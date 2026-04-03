"""
LanScreenMonitor V1 - 日志初始化
"""

import logging
import os
import sys
from config import LOG_DIR, LOG_FILE, APP_NAME


def setup_logging() -> logging.Logger:
    """初始化全局日志：同时输出到文件和控制台。"""
    os.makedirs(LOG_DIR, exist_ok=True)

    logger = logging.getLogger(APP_NAME)
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-7s %(name)s.%(module)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 文件
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # 控制台
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    return logger
