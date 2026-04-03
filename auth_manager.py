"""
LanScreenMonitor V1 - 认证管理模块 (AuthManager)
管理用户账号密码的设置、存储、验证。
密码使用 PBKDF2-SHA256 哈希存储，不保存明文。
"""

import hashlib
import json
import logging
import os
import secrets
import threading
import tkinter as tk
from tkinter import messagebox
from typing import Optional, Tuple

from config import APP_NAME

logger = logging.getLogger(APP_NAME)

# 认证配置文件路径
AUTH_DIR = os.path.join(os.environ.get("LOCALAPPDATA", "."), APP_NAME)
AUTH_FILE = os.path.join(AUTH_DIR, "auth.json")

# PBKDF2 参数
PBKDF2_ITERATIONS = 260_000
SALT_BYTES = 32


def _hash_password(password: str, salt: Optional[bytes] = None) -> Tuple[str, str]:
    """
    使用 PBKDF2-SHA256 哈希密码。
    返回 (hash_hex, salt_hex)。
    """
    if salt is None:
        salt = secrets.token_bytes(SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return dk.hex(), salt.hex()


def _verify_password(password: str, hash_hex: str, salt_hex: str) -> bool:
    """验证密码是否匹配。"""
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return secrets.compare_digest(dk.hex(), hash_hex)


class AuthManager:
    """
    用户认证管理器：
    - 本地文件存储账号和哈希密码
    - 首次启动弹窗设置
    - 验证登录凭据
    """

    def __init__(self):
        self._username: Optional[str] = None
        self._password_hash: Optional[str] = None
        self._salt: Optional[str] = None
        self._loaded = False

    # ─── 持久化 ──────────────────────────────────────

    def load(self) -> bool:
        """
        从本地文件加载认证信息。
        返回 True 表示已有保存的凭据，False 表示需要首次设置。
        """
        if not os.path.isfile(AUTH_FILE):
            logger.info("未找到认证配置，需要首次设置账号密码")
            return False

        try:
            with open(AUTH_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._username = data.get("username")
            self._password_hash = data.get("password_hash")
            self._salt = data.get("salt")

            if not all([self._username, self._password_hash, self._salt]):
                logger.warning("认证配置文件不完整，需要重新设置")
                return False

            self._loaded = True
            logger.info(f"已加载认证配置 (用户: {self._username})")
            return True

        except Exception as e:
            logger.error(f"加载认证配置失败: {e}")
            return False

    def save(self) -> None:
        """保存认证信息到本地文件。"""
        os.makedirs(AUTH_DIR, exist_ok=True)
        data = {
            "username": self._username,
            "password_hash": self._password_hash,
            "salt": self._salt,
        }
        try:
            with open(AUTH_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("认证配置已保存")
        except Exception as e:
            logger.error(f"保存认证配置失败: {e}")

    # ─── 设置凭据 ────────────────────────────────────

    def set_credentials(self, username: str, password: str) -> None:
        """设置账号密码（会自动哈希并保存）。"""
        self._username = username.strip()
        self._password_hash, self._salt = _hash_password(password)
        self._loaded = True
        self.save()
        logger.info(f"认证凭据已设置 (用户: {self._username})")

    # ─── 验证 ────────────────────────────────────────

    def verify(self, username: str, password: str) -> bool:
        """验证账号密码是否正确。"""
        if not self._loaded or not self._username or not self._password_hash or not self._salt:
            return False

        if username.strip() != self._username:
            return False

        return _verify_password(password, self._password_hash, self._salt)

    @property
    def is_configured(self) -> bool:
        """是否已配置账号密码。"""
        return self._loaded and bool(self._username)

    @property
    def username(self) -> Optional[str]:
        return self._username

    # ─── GUI：首次设置弹窗 ───────────────────────────

    def prompt_setup(self) -> bool:
        """
        弹出 tkinter 对话框让用户设置账号密码。
        返回 True 表示设置成功，False 表示用户取消。
        在主线程中调用。
        """
        result = {"ok": False}

        root = tk.Tk()
        root.title(f"{APP_NAME} - 设置登录账号")
        root.resizable(False, False)
        root.attributes("-topmost", True)

        # 居中窗口
        w, h = 420, 340
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        # ─── 标题 ───────────────
        title_frame = tk.Frame(root, padx=20, pady=15)
        title_frame.pack(fill=tk.X)
        tk.Label(
            title_frame,
            text="🔐 设置监控登录账号",
            font=("Microsoft YaHei", 14, "bold"),
        ).pack()
        tk.Label(
            title_frame,
            text="手机端需要输入此账号密码才能观看屏幕",
            font=("Microsoft YaHei", 9),
            fg="#666666",
        ).pack(pady=(5, 0))

        # ─── 表单 ───────────────
        form_frame = tk.Frame(root, padx=30, pady=5)
        form_frame.pack(fill=tk.X)

        tk.Label(form_frame, text="账号:", font=("Microsoft YaHei", 10)).grid(
            row=0, column=0, sticky=tk.W, pady=8
        )
        username_var = tk.StringVar(value="admin")
        username_entry = tk.Entry(form_frame, textvariable=username_var, font=("Consolas", 11), width=25)
        username_entry.grid(row=0, column=1, pady=8, padx=(10, 0))

        tk.Label(form_frame, text="密码:", font=("Microsoft YaHei", 10)).grid(
            row=1, column=0, sticky=tk.W, pady=8
        )
        password_var = tk.StringVar()
        password_entry = tk.Entry(form_frame, textvariable=password_var, font=("Consolas", 11),
                                  width=25, show="*")
        password_entry.grid(row=1, column=1, pady=8, padx=(10, 0))

        tk.Label(form_frame, text="确认密码:", font=("Microsoft YaHei", 10)).grid(
            row=2, column=0, sticky=tk.W, pady=8
        )
        confirm_var = tk.StringVar()
        confirm_entry = tk.Entry(form_frame, textvariable=confirm_var, font=("Consolas", 11),
                                 width=25, show="*")
        confirm_entry.grid(row=2, column=1, pady=8, padx=(10, 0))

        # ─── 错误提示 ───────────
        err_var = tk.StringVar()
        err_label = tk.Label(root, textvariable=err_var, fg="red", font=("Microsoft YaHei", 9))
        err_label.pack(pady=(5, 0))

        # ─── 按钮 ───────────────
        def on_submit():
            u = username_var.get().strip()
            p = password_var.get()
            c = confirm_var.get()

            if not u:
                err_var.set("请输入账号")
                return
            if len(u) < 2:
                err_var.set("账号至少 2 个字符")
                return
            if not p:
                err_var.set("请输入密码")
                return
            if len(p) < 4:
                err_var.set("密码至少 4 个字符")
                return
            if p != c:
                err_var.set("两次输入的密码不一致")
                return

            self.set_credentials(u, p)
            result["ok"] = True
            root.destroy()

        def on_cancel():
            root.destroy()

        btn_frame = tk.Frame(root, padx=30, pady=15)
        btn_frame.pack(fill=tk.X)

        tk.Button(
            btn_frame, text="✅ 确认设置", command=on_submit,
            font=("Microsoft YaHei", 11), width=14, bg="#4CAF50", fg="white",
        ).pack(side=tk.LEFT, padx=5)

        tk.Button(
            btn_frame, text="取消退出", command=on_cancel,
            font=("Microsoft YaHei", 11), width=14,
        ).pack(side=tk.RIGHT, padx=5)

        # Enter 键提交
        root.bind("<Return>", lambda e: on_submit())
        password_entry.focus_set()

        root.mainloop()
        return result["ok"]

    def prompt_change_password(self, parent=None) -> bool:
        """
        弹出修改密码对话框。
        parent: 可选的父窗口，如果提供则使用 Toplevel（避免多 Tk 冲突）。
        返回 True 表示修改成功。
        """
        result = {"ok": False}

        if parent:
            root = tk.Toplevel(parent)
        else:
            root = tk.Tk()
        root.title(f"{APP_NAME} - 修改密码")
        root.resizable(False, False)
        root.attributes("-topmost", True)

        w, h = 460, 480
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        if parent:
            root.grab_set()
            root.transient(parent)

        # ─── 标题 ───────────
        title_frame = tk.Frame(root, padx=20, pady=12)
        title_frame.pack(fill=tk.X)
        tk.Label(
            title_frame,
            text="🔐 修改密码",
            font=("Microsoft YaHei", 13, "bold"),
        ).pack()

        form_frame = tk.Frame(root, padx=30, pady=10)
        form_frame.pack(fill=tk.X)

        tk.Label(form_frame, text=f"当前账号: {self._username}", font=("Microsoft YaHei", 10)).grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=8
        )

        tk.Label(form_frame, text="旧密码:", font=("Microsoft YaHei", 10)).grid(
            row=1, column=0, sticky=tk.W, pady=8
        )
        old_var = tk.StringVar()
        tk.Entry(form_frame, textvariable=old_var, font=("Consolas", 11), width=22, show="*").grid(
            row=1, column=1, pady=8, padx=(10, 0)
        )

        tk.Label(form_frame, text="新密码:", font=("Microsoft YaHei", 10)).grid(
            row=2, column=0, sticky=tk.W, pady=8
        )
        new_var = tk.StringVar()
        tk.Entry(form_frame, textvariable=new_var, font=("Consolas", 11), width=22, show="*").grid(
            row=2, column=1, pady=8, padx=(10, 0)
        )

        tk.Label(form_frame, text="确认新密码:", font=("Microsoft YaHei", 10)).grid(
            row=3, column=0, sticky=tk.W, pady=8
        )
        confirm_var = tk.StringVar()
        tk.Entry(form_frame, textvariable=confirm_var, font=("Consolas", 11), width=22, show="*").grid(
            row=3, column=1, pady=8, padx=(10, 0)
        )

        err_var = tk.StringVar()
        tk.Label(root, textvariable=err_var, fg="red", font=("Microsoft YaHei", 9)).pack(pady=(5, 0))

        def on_submit():
            old_pw = old_var.get()
            new_pw = new_var.get()
            confirm_pw = confirm_var.get()

            if not self.verify(self._username, old_pw):
                err_var.set("旧密码不正确")
                return
            if len(new_pw) < 4:
                err_var.set("新密码至少 4 个字符")
                return
            if new_pw != confirm_pw:
                err_var.set("两次输入的新密码不一致")
                return

            self.set_credentials(self._username, new_pw)
            result["ok"] = True
            root.destroy()

        btn_frame = tk.Frame(root, padx=30, pady=15)
        btn_frame.pack(fill=tk.X)

        tk.Button(btn_frame, text="✅ 确认修改", command=on_submit,
                  font=("Microsoft YaHei", 10), width=14, bg="#4CAF50", fg="white").pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="取消", command=root.destroy,
                  font=("Microsoft YaHei", 10), width=14).pack(side=tk.RIGHT, padx=5)

        root.bind("<Return>", lambda e: on_submit())

        if parent:
            root.wait_window()
        else:
            root.mainloop()
        return result["ok"]

    def prompt_reset_password(self, parent=None) -> bool:
        """
        弹出重置账号密码对话框（用于忘记密码）。
        parent: 可选的父窗口，如果提供则使用 Toplevel。
        返回 True 表示重置成功。
        """
        ask_parent = parent if parent else None
        if not messagebox.askyesno(APP_NAME, "确定要重置账号密码吗？\n\n重置后需要重新登录。", parent=ask_parent):
            return False

        result = {"ok": False}

        if parent:
            root = tk.Toplevel(parent)
        else:
            root = tk.Tk()
        root.title(f"{APP_NAME} - 重置账号密码")
        root.resizable(False, False)
        root.attributes("-topmost", True)

        w, h = 440, 400
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        if parent:
            root.grab_set()
            root.transient(parent)

        title_frame = tk.Frame(root, padx=20, pady=12)
        title_frame.pack(fill=tk.X)
        tk.Label(
            title_frame,
            text="🧩 重置登录账号密码",
            font=("Microsoft YaHei", 13, "bold"),
        ).pack()
        tk.Label(
            title_frame,
            text="忘记密码时使用，重置后请使用新账号登录",
            font=("Microsoft YaHei", 9),
            fg="#666666",
        ).pack(pady=(5, 0))

        form_frame = tk.Frame(root, padx=30, pady=5)
        form_frame.pack(fill=tk.X)

        tk.Label(form_frame, text="账号:", font=("Microsoft YaHei", 10)).grid(
            row=0, column=0, sticky=tk.W, pady=8
        )
        username_var = tk.StringVar(value=self._username or "admin")
        tk.Entry(form_frame, textvariable=username_var, font=("Consolas", 11), width=25).grid(
            row=0, column=1, pady=8, padx=(10, 0)
        )

        tk.Label(form_frame, text="新密码:", font=("Microsoft YaHei", 10)).grid(
            row=1, column=0, sticky=tk.W, pady=8
        )
        password_var = tk.StringVar()
        tk.Entry(form_frame, textvariable=password_var, font=("Consolas", 11),
                 width=25, show="*").grid(
            row=1, column=1, pady=8, padx=(10, 0)
        )

        tk.Label(form_frame, text="确认密码:", font=("Microsoft YaHei", 10)).grid(
            row=2, column=0, sticky=tk.W, pady=8
        )
        confirm_var = tk.StringVar()
        tk.Entry(form_frame, textvariable=confirm_var, font=("Consolas", 11),
                 width=25, show="*").grid(
            row=2, column=1, pady=8, padx=(10, 0)
        )

        err_var = tk.StringVar()
        tk.Label(root, textvariable=err_var, fg="red", font=("Microsoft YaHei", 9)).pack(pady=(5, 0))

        def on_submit():
            u = username_var.get().strip()
            p = password_var.get()
            c = confirm_var.get()

            if not u:
                err_var.set("请输入账号")
                return
            if len(u) < 2:
                err_var.set("账号至少 2 个字符")
                return
            if not p:
                err_var.set("请输入新密码")
                return
            if len(p) < 4:
                err_var.set("密码至少 4 个字符")
                return
            if p != c:
                err_var.set("两次输入的密码不一致")
                return

            self.set_credentials(u, p)
            result["ok"] = True
            root.destroy()

        btn_frame = tk.Frame(root, padx=30, pady=10)
        btn_frame.pack(fill=tk.X)

        tk.Button(btn_frame, text="确认重置", command=on_submit,
                  font=("Microsoft YaHei", 10), width=12, bg="#FF9800", fg="white").pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="取消", command=root.destroy,
                  font=("Microsoft YaHei", 10), width=12).pack(side=tk.RIGHT, padx=5)

        root.bind("<Return>", lambda e: on_submit())

        if parent:
            root.wait_window()
        else:
            root.mainloop()
        return result["ok"]
