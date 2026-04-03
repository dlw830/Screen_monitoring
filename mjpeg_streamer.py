"""
LanScreenMonitor V1 - MJPEG 降级流模块
当 WebRTC 不可用时，提供 MJPEG 流作为兜底方案。
"""

import asyncio
import logging
import time

from aiohttp import web

from config import APP_NAME, PROFILES
from screen_capture import ScreenCapture

logger = logging.getLogger(APP_NAME)

# MJPEG boundary
MJPEG_BOUNDARY = b"--frame"


class MjpegStreamer:
    """
    MJPEG 流推送器：
    - 从 ScreenCapture 拉最新帧
    - 按当前 profile fps 输出 JPEG boundary 流
    """

    def __init__(self, capture: ScreenCapture):
        self._capture = capture

    async def get_mjpeg_stream(self, request: web.Request) -> web.StreamResponse:
        """
        返回 aiohttp StreamResponse 的 MJPEG 流。
        客户端断开时自动停止。
        """
        response = web.StreamResponse(
            status=200,
            reason="OK",
            headers={
                "Content-Type": "multipart/x-mixed-replace; boundary=frame",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
                "Access-Control-Allow-Origin": "*",
            },
        )
        await response.prepare(request)

        # 注册为活跃客户端
        self._capture.add_client()
        client_ip = request.remote or "unknown"
        logger.info(f"MJPEG 客户端连接: {client_ip}")

        try:
            profile = PROFILES.get(self._capture.profile_id, PROFILES["smooth"])
            target_fps = profile["fps"]

            while True:
                frame_start = time.time()

                jpeg_bytes = self._capture.get_latest_frame_jpeg(quality=70)
                if jpeg_bytes is not None:
                    try:
                        await response.write(
                            MJPEG_BOUNDARY + b"\r\n"
                            b"Content-Type: image/jpeg\r\n"
                            b"Content-Length: " + str(len(jpeg_bytes)).encode() + b"\r\n\r\n"
                            + jpeg_bytes + b"\r\n"
                        )
                    except (ConnectionResetError, ConnectionAbortedError, asyncio.CancelledError):
                        break

                # 帧率控制
                elapsed = time.time() - frame_start
                sleep_time = (1.0 / target_fps) - elapsed
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

        except Exception as e:
            logger.debug(f"MJPEG 流异常断开 ({client_ip}): {e}")
        finally:
            self._capture.remove_client()
            logger.info(f"MJPEG 客户端断开: {client_ip}")

        return response
