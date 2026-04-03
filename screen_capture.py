"""
LanScreenMonitor V1 - 屏幕采集模块 (ScreenCapture)
使用 mss 采集主显示器，线程安全、按需推帧。
"""

import logging
import threading
import time
from typing import Optional

import cv2
import mss
import numpy as np

from config import APP_NAME, PROFILES, DEFAULT_PROFILE, OVERLOAD_THRESHOLD_RATIO, OVERLOAD_DURATION_SECONDS, \
    PROFILE_DEGRADE_ORDER

logger = logging.getLogger(APP_NAME)


class ScreenCapture:
    """
    屏幕采集器：
    - 使用 mss 捕获主显示器画面
    - 按照当前 profile 缩放帧分辨率
    - 通过 get_latest_frame() 提供最新帧（线程安全）
    - 按需启停：有客户端时才真正采集
    """

    def __init__(self):
        self._profile_id: str = DEFAULT_PROFILE
        self._profile: dict = PROFILES[DEFAULT_PROFILE]
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # 最新帧（BGR numpy array）
        self._latest_frame: Optional[np.ndarray] = None
        self._frame_lock = threading.Lock()

        # fps 统计（用于过载检测）
        self._fps_counter = 0
        self._fps_last_check = 0.0
        self._actual_fps = 0.0
        self._overload_start: Optional[float] = None

        # 活跃客户端计数（用于按需采集）
        self._active_clients = 0
        self._clients_lock = threading.Lock()

        # 降级回调（通知外部当前 profile 变化）
        self.on_profile_degraded = None  # callable(new_profile_id)

    # ─── 公共接口 ─────────────────────────────────────

    def start(self) -> None:
        """启动采集线程。"""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._capture_loop, daemon=True, name="ScreenCapture")
            self._thread.start()
            logger.info(f"屏幕采集已启动 (profile={self._profile_id})")

    def stop(self) -> None:
        """停止采集线程。"""
        with self._lock:
            self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        self._latest_frame = None
        logger.info("屏幕采集已停止")

    def get_latest_frame(self) -> Optional[np.ndarray]:
        """获取最新采集帧（BGR numpy），无帧返回 None。"""
        with self._frame_lock:
            return self._latest_frame

    def get_latest_frame_jpeg(self, quality: int = 80) -> Optional[bytes]:
        """获取最新帧的 JPEG 编码字节，无帧返回 None。"""
        frame = self.get_latest_frame()
        if frame is None:
            return None
        ret, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ret:
            return None
        return buf.tobytes()

    def set_profile(self, profile_id: str) -> bool:
        """切换 profile。返回是否成功。"""
        if profile_id not in PROFILES:
            return False
        self._profile_id = profile_id
        self._profile = PROFILES[profile_id]
        self._overload_start = None  # 重置过载计时
        logger.info(f"Profile 切换到: {profile_id}")
        return True

    @property
    def profile_id(self) -> str:
        return self._profile_id

    @property
    def actual_fps(self) -> float:
        return self._actual_fps

    def add_client(self) -> None:
        """注册一个活跃客户端。"""
        with self._clients_lock:
            self._active_clients += 1
            logger.debug(f"活跃客户端数: {self._active_clients}")

    def remove_client(self) -> None:
        """注销一个活跃客户端。"""
        with self._clients_lock:
            self._active_clients = max(0, self._active_clients - 1)
            logger.debug(f"活跃客户端数: {self._active_clients}")

    @property
    def has_clients(self) -> bool:
        with self._clients_lock:
            return self._active_clients > 0

    # ─── 内部采集循环 ─────────────────────────────────

    def _capture_loop(self) -> None:
        """持续采集主显示器画面的内部线程。"""
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[0]  # 主显示器（所有屏幕的合并区域其实是 monitors[0]，monitors[1] 是主屏）
                # 使用 monitors[1] 为 primary monitor
                if len(sct.monitors) > 1:
                    monitor = sct.monitors[1]

                self._fps_last_check = time.time()
                self._fps_counter = 0

                while self._running:
                    # 按需采集：无客户端时休眠
                    if not self.has_clients:
                        time.sleep(0.1)
                        continue

                    target_fps = self._profile["fps"]
                    frame_interval = 1.0 / target_fps
                    frame_start = time.time()

                    # 截屏
                    try:
                        raw = sct.grab(monitor)
                    except Exception as e:
                        logger.error(f"截屏失败: {e}")
                        time.sleep(0.5)
                        continue

                    # 转换为 numpy BGR
                    img = np.array(raw)
                    # mss 返回 BGRA，转 BGR
                    img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

                    # 缩放到 profile 尺寸
                    target_w = self._profile["width"]
                    target_h = self._profile["height"]
                    if img.shape[1] != target_w or img.shape[0] != target_h:
                        img = cv2.resize(img, (target_w, target_h), interpolation=cv2.INTER_LINEAR)

                    # 更新最新帧
                    with self._frame_lock:
                        self._latest_frame = img

                    # fps 统计
                    self._fps_counter += 1
                    now = time.time()
                    elapsed = now - self._fps_last_check
                    if elapsed >= 1.0:
                        self._actual_fps = self._fps_counter / elapsed
                        self._fps_counter = 0
                        self._fps_last_check = now
                        self._check_overload(target_fps)

                    # 帧间隔控制
                    frame_elapsed = time.time() - frame_start
                    sleep_time = frame_interval - frame_elapsed
                    if sleep_time > 0:
                        time.sleep(sleep_time)

        except Exception as e:
            logger.exception(f"采集线程异常退出: {e}")
        finally:
            self._running = False

    def _check_overload(self, target_fps: float) -> None:
        """过载检测：实际 fps < 目标 60% 持续 3 秒则自动降档。"""
        threshold = target_fps * OVERLOAD_THRESHOLD_RATIO
        if self._actual_fps < threshold:
            if self._overload_start is None:
                self._overload_start = time.time()
            elif (time.time() - self._overload_start) >= OVERLOAD_DURATION_SECONDS:
                self._auto_degrade()
                self._overload_start = None
        else:
            self._overload_start = None

    def _auto_degrade(self) -> None:
        """自动降级到下一个更低的 profile。"""
        try:
            idx = PROFILE_DEGRADE_ORDER.index(self._profile_id)
        except ValueError:
            return
        if idx + 1 < len(PROFILE_DEGRADE_ORDER):
            new_profile = PROFILE_DEGRADE_ORDER[idx + 1]
            logger.warning(f"性能不足，自动降级: {self._profile_id} -> {new_profile}")
            self.set_profile(new_profile)
            if self.on_profile_degraded:
                try:
                    self.on_profile_degraded(new_profile)
                except Exception:
                    pass
