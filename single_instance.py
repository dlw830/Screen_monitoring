"""
LanScreenMonitor V1 - 单实例锁 (Windows)
使用命名互斥体防止多实例运行。
"""

import ctypes
import logging
import sys
from typing import Optional

from config import APP_NAME

logger = logging.getLogger(APP_NAME)

# Windows API
_kernel32 = ctypes.windll.kernel32  # type: ignore
_ERROR_ALREADY_EXISTS = 183


class SingleInstanceLock:
    """
    Windows 命名互斥体单实例锁。
    使用 with 语句或手动 acquire / release。
    """

    def __init__(self, name: str = f"Global\\{APP_NAME}_Lock"):
        self._name = name
        self._handle: Optional[int] = None

    def acquire(self) -> bool:
        """
        尝试获取锁。
        返回 True 表示成功（当前是唯一实例），
        返回 False 表示已有实例在运行。
        """
        self._handle = _kernel32.CreateMutexW(None, False, self._name)
        if _kernel32.GetLastError() == _ERROR_ALREADY_EXISTS:
            logger.warning("检测到另一个 LanScreenMonitor 实例正在运行")
            return False
        logger.debug("单实例锁获取成功")
        return True

    def release(self) -> None:
        """释放锁。"""
        if self._handle:
            _kernel32.CloseHandle(self._handle)
            self._handle = None

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError("已有另一个 LanScreenMonitor 实例在运行，请先关闭后再试。")
        return self

    def __exit__(self, *args):
        self.release()
