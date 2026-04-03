"""
LanScreenMonitor V1 - Token 管理模块
生成、验证、刷新 URL-safe 临时 token，并含限流逻辑。
"""

import logging
import secrets
import time
from collections import defaultdict
from typing import Optional

from config import APP_NAME, TOKEN_BYTES, TOKEN_TTL_SECONDS, RATE_LIMIT_PER_MINUTE

logger = logging.getLogger(APP_NAME)


class TokenManager:
    """
    管理单个活跃 token 的生命周期。
    - issue_token()  : 生成新 token
    - validate(token): 验证是否有效（含 TTL）
    - refresh()      : 刷新 token（旧立即失效）
    """

    def __init__(self):
        self._token: Optional[str] = None
        self._issued_at: float = 0.0
        # 限流计数器: {ip: [(timestamp, ...), ...]}
        self._fail_counter: dict = defaultdict(list)

    # ─── 核心方法 ─────────────────────────────────────

    def issue_token(self) -> str:
        """生成新 token 并设置颁发时间。"""
        self._token = secrets.token_urlsafe(TOKEN_BYTES)
        self._issued_at = time.time()
        logger.info("已生成新 token (不记录明文)")
        return self._token

    def validate(self, token: Optional[str]) -> bool:
        """验证 token 是否有效（非空、匹配、未过期新连接）。"""
        if not token or not self._token:
            return False
        return secrets.compare_digest(token, self._token) and not self.is_expired()

    def is_expired(self) -> bool:
        """当前 token 是否已过 TTL。"""
        if self._token is None:
            return True
        return (time.time() - self._issued_at) > TOKEN_TTL_SECONDS

    def refresh(self) -> str:
        """刷新 token：旧 token 立即失效，返回新 token。"""
        old = self._token
        new = self.issue_token()
        if old:
            logger.info("Token 已刷新，旧 token 立即失效")
        return new

    @property
    def current_token(self) -> Optional[str]:
        return self._token

    @property
    def remaining_ttl(self) -> float:
        """剩余有效秒数。"""
        if self._token is None:
            return 0.0
        r = TOKEN_TTL_SECONDS - (time.time() - self._issued_at)
        return max(r, 0.0)

    # ─── 限流 ────────────────────────────────────────

    def record_fail(self, client_ip: str) -> None:
        """记录一次非法访问。"""
        now = time.time()
        self._fail_counter[client_ip].append(now)

    def is_rate_limited(self, client_ip: str) -> bool:
        """检查该 IP 是否超过限流阈值。"""
        now = time.time()
        window_start = now - 60.0
        # 清理旧记录
        self._fail_counter[client_ip] = [
            t for t in self._fail_counter[client_ip] if t > window_start
        ]
        return len(self._fail_counter[client_ip]) >= RATE_LIMIT_PER_MINUTE
