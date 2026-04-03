"""
LanScreenMonitor V1 - 全局常量与配置
零配置设计：所有配置项以常量形式定义在此文件，无需外部配置文件。
"""

import os

# ─── 版本 ───────────────────────────────────────────────
VERSION = "1.0.0"
APP_NAME = "LanScreenMonitor"

# ─── 网络 ───────────────────────────────────────────────
DEFAULT_PORT = 9000
PORT_SCAN_TRIES = 50           # 端口自动递增探测次数

# ─── Token / 安全 ────────────────────────────────────────
TOKEN_BYTES = 32               # token 随机字节数 (URL-safe base64 ≈ 43 字符)
TOKEN_TTL_SECONDS = 600        # 10 分钟
RATE_LIMIT_PER_MINUTE = 20     # 同 IP 每分钟最大非法访问次数

# ─── 推流 / 性能 ─────────────────────────────────────────
MAX_CLIENTS = 3

PROFILES = {
    "smooth": {"width": 1280, "height": 720,  "fps": 15, "bitrate": 1_500_000},
    "hd":     {"width": 1920, "height": 1080, "fps": 30, "bitrate": 4_000_000},
    "low":    {"width": 854,  "height": 480,  "fps": 10, "bitrate": 800_000},
}
DEFAULT_PROFILE = "smooth"

# 过载降级：实际 fps 低于目标 60% 持续此秒数后自动切换
OVERLOAD_THRESHOLD_RATIO = 0.6
OVERLOAD_DURATION_SECONDS = 3.0

# ─── 日志 ───────────────────────────────────────────────
LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA", "."), APP_NAME, "logs")
LOG_FILE = os.path.join(LOG_DIR, "app.log")

# ─── WebRTC ─────────────────────────────────────────────
WEBRTC_TIMEOUT_SECONDS = 5    # 前端 WebRTC 超时后降级 MJPEG 的秒数（前端用）

# ─── 降级策略映射 ────────────────────────────────────────
PROFILE_DEGRADE_ORDER = ["hd", "smooth", "low"]  # 从高到低

# ─── 认证 ───────────────────────────────────────────────
AUTH_DIR = os.path.join(os.environ.get("LOCALAPPDATA", "."), APP_NAME)
AUTH_FILE = os.path.join(AUTH_DIR, "auth.json")
LOGIN_MAX_ATTEMPTS_PER_MINUTE = 10  # 同 IP 每分钟最多登录尝试次数
