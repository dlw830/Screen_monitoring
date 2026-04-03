"""
LanScreenMonitor V1 - 主入口 (App)
零配置：双击 exe 即启动全部服务。
"""

import asyncio
import logging
import os
import signal
import sys
import threading
import time
from typing import Optional

from config import APP_NAME, VERSION, LOG_FILE
from log_setup import setup_logging
from single_instance import SingleInstanceLock
from net_selector import NetSelector
from token_manager import TokenManager
from auth_manager import AuthManager
from screen_capture import ScreenCapture
from webrtc_manager import WebRTCSessionManager
from mjpeg_streamer import MjpegStreamer
from web_server import WebServer
from qr_window import QRCodeWindow
from splash_window import SplashWindow

logger: Optional[logging.Logger] = None


class App:
    """
    应用主协调器：
    1. 单实例锁
    2. 选择 IP / 端口
    3. 生成 Token
    4. 启动 Web 服务 + 采集 + 推流
    5. 显示二维码弹窗
    6. 控制台热键
    """

    def __init__(self):
        self._lock = SingleInstanceLock()
        self._net = NetSelector()
        self._token_mgr = TokenManager()
        self._auth_mgr = AuthManager()
        self._capture = ScreenCapture()
        self._rtc: Optional[WebRTCSessionManager] = None
        self._mjpeg: Optional[MjpegStreamer] = None
        self._server: Optional[WebServer] = None
        self._qr_window: Optional[QRCodeWindow] = None
        self._splash: Optional[SplashWindow] = None
        self._ip: str = ""
        self._port: int = 0
        self._url: str = ""
        self._running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def start(self) -> None:
        """启动整个应用（同步调用，内部运行事件循环）。"""
        global logger
        logger = setup_logging()
        logger.info(f"{'=' * 50}")
        logger.info(f"{APP_NAME} v{VERSION} 启动中...")
        logger.info(f"日志文件: {LOG_FILE}")
        logger.info(f"{'=' * 50}")

        # 1. 单实例锁
        if not self._lock.acquire():
            self._show_error("已有另一个 LanScreenMonitor 实例在运行，请先关闭后再试。")
            sys.exit(1)

        try:
            # 2. 设置账号密码（首次启动或尚未配置）
            if not self._auth_mgr.load():
                logger.info("首次启动，需要设置登录账号密码")
                if not self._auth_mgr.prompt_setup():
                    logger.info("用户取消设置，退出")
                    sys.exit(0)

            # 启动画面（科技感 · 主线程同步显示，至少 5 秒）
            splash_start = time.monotonic()
            self._show_splash()

            # 3. 选择 IP
            self._update_splash("正在检测局域网 IP...")
            self._ip = self._net.select_best_ipv4()

            # 4. 选择端口
            self._update_splash("正在绑定端口...")
            self._port = self._net.bind_available_port()

            # 5. 生成 Token（登录后服务端颁发，不再放入 URL）
            self._update_splash("正在生成访问令牌...")
            self._token_mgr.issue_token()
            self._url = f"http://{self._ip}:{self._port}/"

            logger.info(f"访问地址: {self._url}")

            # 6. 初始化各模块
            self._update_splash("正在初始化 WebRTC / MJPEG...")
            self._rtc = WebRTCSessionManager(self._capture)
            self._mjpeg = MjpegStreamer(self._capture)

            # 过载降级回调：通知所有 WebRTC 会话
            self._capture.on_profile_degraded = self._on_profile_degraded

            # 7. 启动屏幕采集
            self._update_splash("正在启动屏幕采集...")
            self._capture.start()

            # 确保启动画面至少显示 5 秒
            self._update_splash("即将就绪...")
            elapsed = time.monotonic() - splash_start
            remaining = 5.0 - elapsed
            if remaining > 0:
                end_time = time.monotonic() + remaining
                while time.monotonic() < end_time:
                    self._update_splash()
                    time.sleep(0.05)

            # 8. 关闭启动画面并显示二维码弹窗
            self._close_splash()
            self._show_qr_window()

            # 9. 打印控制台提示
            self._print_console_help()

            # 10. 启动 Web 服务 + 控制台热键（事件循环）
            self._running = True
            self._run_event_loop()

        except Exception as e:
            logger.exception(f"启动失败: {e}")
            self._show_error(f"启动失败: {e}\n\n日志文件: {LOG_FILE}\n\n常见排查项:\n- 端口被占用\n- 防火墙阻止\n- 请确保在同一局域网内")
        finally:
            self.stop()

    def stop(self) -> None:
        """停止所有服务并释放资源。"""
        logger_to_use = logger or logging.getLogger(APP_NAME)
        logger_to_use.info("正在关闭...")
        self._running = False

        # 关闭启动画面
        self._close_splash()

        # 关闭采集
        self._capture.stop()

        # 关闭弹窗
        if self._qr_window:
            self._qr_window.close()

        # 关闭 Web 服务和 WebRTC 需要在事件循环中执行
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._async_stop(), self._loop)

        # 释放单实例锁
        self._lock.release()
        logger_to_use.info(f"{APP_NAME} 已退出")

    async def _async_stop(self) -> None:
        """异步停止 Web 服务和 WebRTC。"""
        if self._rtc:
            await self._rtc.close_all()
        if self._server:
            await self._server.stop()

    def _run_event_loop(self) -> None:
        """运行 asyncio 事件循环 + 控制台热键。"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        # 启动控制台热键监听线程
        hotkey_thread = threading.Thread(target=self._console_hotkey_loop, daemon=True, name="HotkeyMonitor")
        hotkey_thread.start()

        try:
            self._loop.run_until_complete(self._async_main())
        except KeyboardInterrupt:
            logger.info("收到 Ctrl+C，正在退出...")
        finally:
            # 清理
            try:
                self._loop.run_until_complete(self._async_stop())
            except Exception:
                pass
            self._loop.close()

    async def _async_main(self) -> None:
        """异步主函数：启动 Web 服务器，等待退出信号。"""
        self._server = WebServer(
            token_manager=self._token_mgr,
            auth_manager=self._auth_mgr,
            capture=self._capture,
            rtc_manager=self._rtc,
            mjpeg_streamer=self._mjpeg,
            host="0.0.0.0",
            port=self._port,
        )
        await self._server.start()

        logger.info(f"✅ {APP_NAME} 已就绪！手机扫码即可观看")
        logger.info(f"访问地址: {self._url}")

        # 等待关闭信号
        while self._running:
            await asyncio.sleep(0.5)

    def _console_hotkey_loop(self) -> None:
        """控制台热键监听（阻塞线程）。"""
        while self._running:
            try:
                # Windows 下 input() 会阻塞
                cmd = input().strip().upper()
                if cmd == "R":
                    self._refresh_token()
                elif cmd == "Q":
                    logger.info("用户请求退出 (Q)")
                    self._running = False
                    break
            except EOFError:
                break
            except Exception:
                break

    def _refresh_token(self) -> str:
        """刷新 token（已登录用户的 token 失效，需重新登录）。"""
        self._token_mgr.refresh()
        self._url = f"http://{self._ip}:{self._port}/"
        logger.info(f"Token 已刷新！所有已登录的用户需要重新登录。")

        # 更新弹窗
        if self._qr_window:
            self._qr_window.update_url(self._url)

        return self._url

    def _show_qr_window(self) -> None:
        """显示二维码弹窗。"""
        try:
            self._qr_window = QRCodeWindow(
                url=self._url,
                on_refresh=self._refresh_token,
                on_quit=lambda: setattr(self, "_running", False),
                on_change_password=lambda parent=None: self._auth_mgr.prompt_change_password(parent=parent),
                on_reset_password=lambda parent=None: self._auth_mgr.prompt_reset_password(parent=parent),
                get_auth_username=lambda: self._auth_mgr.username,
                auth_username=self._auth_mgr.username,
            )
            self._qr_window.show()
        except Exception as e:
            logger.warning(f"无法启动 GUI 弹窗: {e}")
            logger.info("请手动访问以下地址:")
            logger.info(f"  {self._url}")

    def _show_splash(self) -> None:
        """在主线程中显示启动画面（同步非阻塞）。"""
        try:
            self._splash = SplashWindow()
            self._splash.show()
        except Exception as e:
            logger.info(f"启动画面显示失败: {e}")
            self._splash = None

    def _update_splash(self, status: str = "") -> None:
        """刷新启动画面（主线程调用）。"""
        if self._splash:
            try:
                self._splash.update(status)
            except Exception:
                pass

    def _close_splash(self) -> None:
        """关闭启动画面。"""
        if self._splash:
            try:
                self._splash.close()
            except Exception:
                pass
            self._splash = None

    def _print_console_help(self) -> None:
        """打印控制台操作提示。"""
        print()
        print("=" * 60)
        print(f"  {APP_NAME} v{VERSION}")
        print("=" * 60)
        print(f"  访问地址: {self._url}")
        print(f"  登录账号: {self._auth_mgr.username}")
        print(f"  局域网 IP: {self._ip}")
        print(f"  端口: {self._port}")
        print("-" * 60)
        print("  控制台命令:")
        print("    R  - 刷新 Token（强制所有用户重新登录）")
        print("    Q  - 退出程序")
        print("-" * 60)
        print("  ⚠ 若手机无法连接，请允许本程序通过 Windows 防火墙")
        print("    路径: Windows 安全中心 → 防火墙 → 允许应用")
        print("=" * 60)
        print()

    def _on_profile_degraded(self, new_profile_id: str) -> None:
        """采集器自动降级时的回调。"""
        logger.warning(f"性能降级通知: 已切换到 {new_profile_id}")

    @staticmethod
    def _show_error(message: str) -> None:
        """显示错误弹窗（兜底控制台输出）。"""
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(APP_NAME, message)
            root.destroy()
        except Exception:
            print(f"\n[错误] {message}")


def main():
    app = App()
    app.start()


if __name__ == "__main__":
    main()
