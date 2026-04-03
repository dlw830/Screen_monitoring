"""
LanScreenMonitor V1 - WebRTC 会话管理模块
使用 aiortc 实现 WebRTC 推流，支持 VP8 编码。
"""

import asyncio
import logging
import time
import uuid
from typing import Dict, Optional

import cv2
import numpy as np
from av import VideoFrame
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate
from aiortc.contrib.media import MediaRelay
from aiortc.mediastreams import MediaStreamTrack

from config import APP_NAME, MAX_CLIENTS, PROFILES, DEFAULT_PROFILE
from screen_capture import ScreenCapture

logger = logging.getLogger(APP_NAME)


class ScreenVideoTrack(MediaStreamTrack):
    """
    自定义 Video Track：从 ScreenCapture 中读取最新帧，
    以目标 fps 推送到 WebRTC peer。
    """
    kind = "video"

    def __init__(self, capture: ScreenCapture, profile_id: str = DEFAULT_PROFILE):
        super().__init__()
        self._capture = capture
        self._profile_id = profile_id
        self._profile = PROFILES[profile_id]
        self._start_time = time.time()
        self._frame_count = 0

    def set_profile(self, profile_id: str) -> None:
        if profile_id in PROFILES:
            self._profile_id = profile_id
            self._profile = PROFILES[profile_id]

    async def recv(self) -> VideoFrame:
        """按帧率节奏返回视频帧。"""
        target_fps = self._profile["fps"]
        frame_interval = 1.0 / target_fps

        # 计算当前帧应该出现的时间
        self._frame_count += 1
        target_time = self._start_time + self._frame_count * frame_interval
        now = time.time()
        wait = target_time - now
        if wait > 0:
            await asyncio.sleep(wait)

        # 获取最新帧
        frame_bgr = self._capture.get_latest_frame()
        if frame_bgr is None:
            # 还没有帧，返回黑帧
            w = self._profile["width"]
            h = self._profile["height"]
            frame_bgr = np.zeros((h, w, 3), dtype=np.uint8)

        # 确保尺寸匹配
        target_w = self._profile["width"]
        target_h = self._profile["height"]
        if frame_bgr.shape[1] != target_w or frame_bgr.shape[0] != target_h:
            frame_bgr = cv2.resize(frame_bgr, (target_w, target_h))

        # BGR -> RGB，创建 VideoFrame
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        video_frame = VideoFrame.from_ndarray(frame_rgb, format="rgb24")

        # 设置 pts 和 time_base
        video_frame.pts = self._frame_count
        video_frame.time_base = f"1/{target_fps}"

        return video_frame


class WebRTCSession:
    """单个 WebRTC 会话。"""

    def __init__(self, session_id: str, client_ip: str, pc: RTCPeerConnection,
                 track: ScreenVideoTrack, profile_id: str):
        self.session_id = session_id
        self.client_ip = client_ip
        self.pc = pc
        self.track = track
        self.profile_id = profile_id
        self.created_at = time.time()


class WebRTCSessionManager:
    """
    管理所有 WebRTC 会话，执行创建、SDP 交换、ICE 交换、断开等操作。
    """

    def __init__(self, capture: ScreenCapture):
        self._capture = capture
        self._sessions: Dict[str, WebRTCSession] = {}
        self._lock = asyncio.Lock()

    @property
    def session_count(self) -> int:
        return len(self._sessions)

    async def create_session(self, client_ip: str, profile_id: str = DEFAULT_PROFILE) -> Optional[str]:
        """
        创建新的 WebRTC 会话。
        返回 session_id 或 None（超过最大连接数时）。
        """
        async with self._lock:
            if len(self._sessions) >= MAX_CLIENTS:
                logger.warning(f"连接数已达上限 ({MAX_CLIENTS})，拒绝 {client_ip}")
                return None

            session_id = str(uuid.uuid4())
            pc = RTCPeerConnection()

            # 创建视频 track
            track = ScreenVideoTrack(self._capture, profile_id)
            pc.addTrack(track)

            # 注册客户端
            self._capture.add_client()

            session = WebRTCSession(session_id, client_ip, pc, track, profile_id)
            self._sessions[session_id] = session

            # 监听连接状态变化
            @pc.on("connectionstatechange")
            async def on_state_change():
                state = pc.connectionState
                logger.info(f"WebRTC session {session_id[:8]} 状态: {state}")
                if state in ("failed", "closed", "disconnected"):
                    await self.close_session(session_id)

            logger.info(f"WebRTC 会话创建: {session_id[:8]} (client={client_ip}, profile={profile_id})")
            return session_id

    async def handle_offer(self, session_id: str, sdp: str) -> Optional[str]:
        """处理 SDP offer，返回 answer SDP 字符串。"""
        session = self._sessions.get(session_id)
        if not session:
            logger.error(f"找不到会话: {session_id[:8]}")
            return None

        offer = RTCSessionDescription(sdp=sdp, type="offer")
        await session.pc.setRemoteDescription(offer)

        answer = await session.pc.createAnswer()
        await session.pc.setLocalDescription(answer)

        logger.info(f"SDP answer 已生成: {session_id[:8]}")
        return session.pc.localDescription.sdp

    async def add_ice(self, session_id: str, candidate_dict: dict) -> None:
        """添加 ICE candidate。"""
        session = self._sessions.get(session_id)
        if not session:
            return

        try:
            candidate = RTCIceCandidate(
                sdpMid=candidate_dict.get("sdpMid"),
                sdpMLineIndex=candidate_dict.get("sdpMLineIndex"),
                candidate=candidate_dict.get("candidate", ""),
            )
            await session.pc.addIceCandidate(candidate)
        except Exception as e:
            logger.debug(f"添加 ICE candidate 失败: {e}")

    async def set_profile(self, session_id: str, profile_id: str) -> bool:
        """切换指定会话的 profile。"""
        session = self._sessions.get(session_id)
        if not session or profile_id not in PROFILES:
            return False
        session.track.set_profile(profile_id)
        session.profile_id = profile_id
        logger.info(f"会话 {session_id[:8]} profile 切换到 {profile_id}")
        return True

    async def close_session(self, session_id: str) -> None:
        """关闭并清理一个会话。"""
        async with self._lock:
            session = self._sessions.pop(session_id, None)
        if session:
            self._capture.remove_client()
            try:
                await session.pc.close()
            except Exception:
                pass
            logger.info(f"WebRTC 会话关闭: {session_id[:8]} (client={session.client_ip})")

    async def close_all(self) -> None:
        """关闭所有会话。"""
        session_ids = list(self._sessions.keys())
        for sid in session_ids:
            await self.close_session(sid)
        logger.info("所有 WebRTC 会话已关闭")

    def get_info(self) -> dict:
        """返回当前会话状态概要。"""
        return {
            "active_sessions": len(self._sessions),
            "max_clients": MAX_CLIENTS,
            "sessions": [
                {
                    "session_id": s.session_id[:8],
                    "client_ip": s.client_ip,
                    "profile": s.profile_id,
                    "duration_s": round(time.time() - s.created_at, 1),
                }
                for s in self._sessions.values()
            ],
        }
