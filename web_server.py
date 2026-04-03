"""
LanScreenMonitor V1 - aiohttp Web 服务器
处理 HTTP 路由、WebSocket 信令、Token 鉴权、限流。
"""

import asyncio
import json
import logging
import os
import sys
from typing import Optional

from aiohttp import web

from config import APP_NAME, VERSION, PROFILES, MAX_CLIENTS, LOGIN_MAX_ATTEMPTS_PER_MINUTE
from token_manager import TokenManager
from auth_manager import AuthManager
from screen_capture import ScreenCapture
from webrtc_manager import WebRTCSessionManager
from mjpeg_streamer import MjpegStreamer

logger = logging.getLogger(APP_NAME)


def _get_web_dir() -> str:
    """获取 web 静态资源目录（兼容 PyInstaller 打包）。"""
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS  # type: ignore
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "web")


class WebServer:
    """
    aiohttp Web 服务器：
    - / : 前端页面（包含登录表单）
    - /health : 健康检查（无需 token）
    - /api/v1/login : 登录认证（无需 token，验证账号密码后返回 token）
    - /ws : WebSocket 信令
    - /mjpeg : MJPEG 降级流
    - /api/v1/info : 状态信息
    - /api/v1/profile : 切换 profile
    - /api/v1/admin/refresh_token : 刷新 token（仅 localhost）
    """

    def __init__(
        self,
        token_manager: TokenManager,
        auth_manager: AuthManager,
        capture: ScreenCapture,
        rtc_manager: WebRTCSessionManager,
        mjpeg_streamer: MjpegStreamer,
        host: str = "0.0.0.0",
        port: int = 9000,
    ):
        self._token_mgr = token_manager
        self._auth_mgr = auth_manager
        self._capture = capture
        self._rtc = rtc_manager
        self._mjpeg = mjpeg_streamer
        self._host = host
        self._port = port
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        # 存储 session_id -> ws 映射（便于推送消息）
        self._ws_sessions: dict = {}  # ws -> session_id
        # 所有活跃的 WebSocket 连接（用于关闭时通知客户端）
        self._active_ws: set = set()

    async def start(self) -> None:
        """启动 Web 服务器。"""
        self._app = web.Application()
        self._setup_routes()

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()
        logger.info(f"Web 服务器已启动: http://{self._host}:{self._port}")

    async def stop(self) -> None:
        """停止 Web 服务器（先通知所有客户端再关闭）。"""
        # 通知所有已连接的 WebSocket 客户端：服务端即将关闭
        for ws in list(self._active_ws):
            try:
                await ws.send_json({"type": "server_shutdown", "message": "服务端已关闭"})
                await ws.close()
            except Exception:
                pass
        self._active_ws.clear()

        if self._runner:
            await self._runner.cleanup()
        logger.info("Web 服务器已停止")

    def _setup_routes(self) -> None:
        app = self._app
        web_dir = _get_web_dir()

        app.router.add_get("/health", self._handle_health)
        app.router.add_post("/api/v1/login", self._handle_login)
        app.router.add_get("/ws", self._handle_ws)
        app.router.add_get("/mjpeg", self._handle_mjpeg)
        app.router.add_get("/api/v1/info", self._handle_info)
        app.router.add_post("/api/v1/profile", self._handle_set_profile)
        app.router.add_post("/api/v1/admin/refresh_token", self._handle_refresh_token)

        # 静态文件 - 前端页面（/ 路径需要特殊处理）
        app.router.add_get("/", self._handle_index)
        if os.path.isdir(web_dir):
            app.router.add_static("/static/", path=web_dir, name="static")

    # ─── Token 验证中间件 ─────────────────────────────

    def _validate_token(self, request: web.Request) -> bool:
        """从查询参数 t 中提取和验证 token。"""
        token = request.query.get("t") or request.headers.get("X-Token")
        return self._token_mgr.validate(token)

    def _check_rate_limit(self, request: web.Request) -> bool:
        """检查是否被限流。"""
        client_ip = request.remote or "unknown"
        return self._token_mgr.is_rate_limited(client_ip)

    def _reject(self, request: web.Request, status: int = 403, msg: str = "Forbidden") -> web.Response:
        """拒绝请求并记录失败。"""
        client_ip = request.remote or "unknown"
        self._token_mgr.record_fail(client_ip)
        logger.warning(f"拒绝访问: {client_ip} -> {request.path} ({msg})")
        return web.json_response({"error": msg}, status=status)

    # ─── 路由处理器 ───────────────────────────────────

    async def _handle_health(self, request: web.Request) -> web.Response:
        """健康检查（无需 token）。"""
        return web.json_response({"status": "ok", "version": VERSION})

    async def _handle_index(self, request: web.Request) -> web.Response:
        """前端页面（登录页 + Viewer）：无需 token 即可访问，登录后获取 token。"""
        web_dir = _get_web_dir()
        index_path = os.path.join(web_dir, "index.html")
        if os.path.isfile(index_path):
            return web.FileResponse(index_path)
        return web.Response(text="前端页面未找到", status=500)

    async def _handle_login(self, request: web.Request) -> web.Response:
        """登录认证：验证账号密码，成功后返回 token。"""
        client_ip = request.remote or "unknown"

        # 登录限流
        if self._token_mgr.is_rate_limited(client_ip):
            logger.warning(f"登录限流: {client_ip}")
            return web.json_response({"error": "登录尝试次数过多，请稍后再试"}, status=429)

        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "无效的请求格式"}, status=400)

        username = body.get("username", "").strip()
        password = body.get("password", "")

        if not username or not password:
            return web.json_response({"error": "请输入账号和密码"}, status=400)

        if self._auth_mgr.verify(username, password):
            # 登录成功，返回当前有效 token（若过期则刷新）
            if self._token_mgr.is_expired():
                self._token_mgr.refresh()
            token = self._token_mgr.current_token
            logger.info(f"用户登录成功: {username} ({client_ip})")
            return web.json_response({"ok": True, "token": token})
        else:
            self._token_mgr.record_fail(client_ip)
            logger.warning(f"登录失败: {username} ({client_ip})")
            return web.json_response({"error": "账号或密码错误"}, status=401)

    async def _handle_mjpeg(self, request: web.Request) -> web.StreamResponse:
        """MJPEG 降级流。"""
        if not self._validate_token(request):
            if self._check_rate_limit(request):
                return self._reject(request, 429, "Too Many Requests")
            return self._reject(request, 403, "无效或过期的访问令牌")

        return await self._mjpeg.get_mjpeg_stream(request)

    async def _handle_info(self, request: web.Request) -> web.Response:
        """返回状态信息。"""
        if not self._validate_token(request):
            if self._check_rate_limit(request):
                return self._reject(request, 429, "Too Many Requests")
            return self._reject(request, 403, "无效或过期的访问令牌")

        info = {
            "version": VERSION,
            "profiles": list(PROFILES.keys()),
            "current_profile": self._capture.profile_id,
            "actual_fps": round(self._capture.actual_fps, 1),
            "webrtc": self._rtc.get_info(),
        }
        return web.json_response(info)

    async def _handle_set_profile(self, request: web.Request) -> web.Response:
        """切换 profile。"""
        if not self._validate_token(request):
            if self._check_rate_limit(request):
                return self._reject(request, 429, "Too Many Requests")
            return self._reject(request, 403, "无效或过期的访问令牌")

        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        profile_id = body.get("profile_id")
        if profile_id not in PROFILES:
            return web.json_response({"error": f"未知 profile: {profile_id}"}, status=400)

        self._capture.set_profile(profile_id)
        return web.json_response({"ok": True, "profile_id": profile_id})

    async def _handle_refresh_token(self, request: web.Request) -> web.Response:
        """刷新 token（仅 localhost 可访问）。"""
        client_ip = request.remote or ""
        if client_ip not in ("127.0.0.1", "::1", "localhost"):
            return web.json_response({"error": "仅限本机访问"}, status=403)

        new_token = self._token_mgr.refresh()
        return web.json_response({"ok": True, "token": new_token})

    # ─── WebSocket 信令 ───────────────────────────────

    async def _handle_ws(self, request: web.Request) -> web.WebSocketResponse:
        """
        WebSocket 信令处理：
        消息类型: client_hello, offer, ice_candidate, set_profile
        """
        # 验证 token
        if not self._validate_token(request):
            if self._check_rate_limit(request):
                return self._reject(request, 429, "Too Many Requests")
            return self._reject(request, 403, "无效或过期的访问令牌")

        ws = web.WebSocketResponse(heartbeat=10.0)  # 10秒心跳检测
        await ws.prepare(request)

        client_ip = request.remote or "unknown"
        session_id: Optional[str] = None
        self._active_ws.add(ws)
        logger.info(f"WebSocket 连接: {client_ip}")

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                    except json.JSONDecodeError:
                        await ws.send_json({"type": "server_error", "code": "INVALID_JSON", "message": "无效 JSON"})
                        continue

                    msg_type = data.get("type")

                    if msg_type == "client_hello":
                        profile_id = data.get("profile_id", "smooth")
                        session_id = await self._rtc.create_session(client_ip, profile_id)
                        if session_id is None:
                            await ws.send_json({
                                "type": "server_error",
                                "code": "MAX_CLIENTS",
                                "message": f"连接数已达上限 ({MAX_CLIENTS})",
                            })
                            await ws.close()
                            break
                        await ws.send_json({"type": "session_created", "session_id": session_id})

                    elif msg_type == "offer":
                        if not session_id:
                            await ws.send_json({"type": "server_error", "code": "NO_SESSION", "message": "请先发送 client_hello"})
                            continue
                        sdp = data.get("sdp")
                        answer_sdp = await self._rtc.handle_offer(session_id, sdp)
                        if answer_sdp:
                            await ws.send_json({"type": "answer", "sdp": answer_sdp})
                        else:
                            await ws.send_json({"type": "server_error", "code": "OFFER_FAILED", "message": "SDP 处理失败"})

                    elif msg_type == "ice_candidate":
                        if session_id:
                            await self._rtc.add_ice(session_id, {
                                "candidate": data.get("candidate", ""),
                                "sdpMid": data.get("sdpMid"),
                                "sdpMLineIndex": data.get("sdpMLineIndex"),
                            })

                    elif msg_type == "set_profile":
                        profile_id = data.get("profile_id")
                        if session_id and profile_id:
                            ok = await self._rtc.set_profile(session_id, profile_id)
                            await ws.send_json({"type": "profile_changed", "ok": ok, "profile_id": profile_id})
                        # 同时切全局采集 profile
                        if profile_id:
                            self._capture.set_profile(profile_id)

                    else:
                        await ws.send_json({"type": "server_error", "code": "UNKNOWN_TYPE", "message": f"未知消息类型: {msg_type}"})

                elif msg.type in (web.WSMsgType.ERROR, web.WSMsgType.CLOSE):
                    break

        except Exception as e:
            logger.error(f"WebSocket 异常 ({client_ip}): {e}")
        finally:
            self._active_ws.discard(ws)
            if session_id:
                await self._rtc.close_session(session_id)
            logger.info(f"WebSocket 断开: {client_ip}")

        return ws
