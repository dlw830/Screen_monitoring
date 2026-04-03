"""
LanScreenMonitor V1 - 二维码弹窗模块 (tkinter)
在独立线程中显示二维码弹窗，支持刷新 token 和退出。
"""

import io
import logging
import threading
import tkinter as tk
from tkinter import messagebox
from typing import Callable, Optional

import qrcode
from PIL import Image, ImageTk

from config import APP_NAME

logger = logging.getLogger(APP_NAME)


class QRCodeWindow:
    """
    Tkinter 二维码弹窗：
    - 显示当前访问 URL 的二维码
    - "复制链接" / "刷新口令" / "修改密码" / "退出" 按钮
    - 在独立线程中运行，不阻塞主事件循环
    """

    def __init__(
        self,
        url: str,
        on_refresh: Optional[Callable[[], str]] = None,
        on_quit: Optional[Callable[[], None]] = None,
        on_change_password: Optional[Callable[[], bool]] = None,
        on_reset_password: Optional[Callable[[], bool]] = None,
        get_auth_username: Optional[Callable[[], Optional[str]]] = None,
        auth_username: Optional[str] = None,
    ):
        self._url = url
        self._on_refresh = on_refresh
        self._on_quit = on_quit
        self._on_change_password = on_change_password
        self._on_reset_password = on_reset_password
        self._get_auth_username = get_auth_username
        self._auth_username = auth_username or ""
        self._root: Optional[tk.Tk] = None
        self._thread: Optional[threading.Thread] = None
        self._qr_label: Optional[tk.Label] = None
        self._url_var: Optional[tk.StringVar] = None
        self._photo: Optional[ImageTk.PhotoImage] = None
        self._auth_var: Optional[tk.StringVar] = None
        self._auth_label: Optional[tk.Label] = None

    def show(self) -> None:
        """在独立线程中启动 GUI 窗口。"""
        self._thread = threading.Thread(target=self._run_gui, daemon=True, name="QRCodeWindow")
        self._thread.start()

    def update_url(self, new_url: str) -> None:
        """更新二维码 URL（线程安全）。"""
        self._url = new_url
        if self._root:
            try:
                self._root.after(0, self._refresh_display)
            except Exception:
                pass

    def close(self) -> None:
        """关闭弹窗。"""
        if self._root:
            try:
                self._root.after(0, self._root.destroy)
            except Exception:
                pass

    def _run_gui(self) -> None:
        """GUI 主循环（在独立线程中运行）。"""
        try:
            self._root = tk.Tk()
            self._root.title(f"{APP_NAME} - 扫码观看")
            self._root.resizable(False, False)
            self._root.protocol("WM_DELETE_WINDOW", self._on_close)

            # 尝试置顶
            self._root.attributes("-topmost", True)

            # ─── URL 显示 ───────────────────────────────
            self._url_var = tk.StringVar(value=self._url)

            top_frame = tk.Frame(self._root, padx=10, pady=5)
            top_frame.pack(fill=tk.X)

            tk.Label(top_frame, text="访问地址:", font=("Microsoft YaHei", 10)).pack(side=tk.LEFT)

            url_entry = tk.Entry(top_frame, textvariable=self._url_var, font=("Consolas", 9),
                                 state="readonly", width=50)
            url_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

            copy_btn = tk.Button(top_frame, text="复制", command=self._copy_url, width=6)
            copy_btn.pack(side=tk.LEFT, padx=2)

            # ─── 二维码图片 ─────────────────────────────
            qr_frame = tk.Frame(self._root, padx=10, pady=10)
            qr_frame.pack()

            self._qr_label = tk.Label(qr_frame)
            self._qr_label.pack()
            self._refresh_display()

            # ─── 提示文字 ───────────────────────────────
            hint_frame = tk.Frame(self._root, padx=10, pady=2)
            hint_frame.pack(fill=tk.X)
            tk.Label(
                hint_frame,
                text="请用手机扫描上方二维码，在同一局域网内浏览器打开并登录即可观看。",
                font=("Microsoft YaHei", 9),
                fg="#666666",
                wraplength=380,
            ).pack()

            # ─── 账号信息显示 ─────────────────────────
            if self._auth_username:
                auth_frame = tk.Frame(self._root, padx=10, pady=2)
                auth_frame.pack(fill=tk.X)
                self._auth_var = tk.StringVar(value=f"👤 登录账号: {self._auth_username}")
                self._auth_label = tk.Label(
                    auth_frame,
                    textvariable=self._auth_var,
                    font=("Microsoft YaHei", 9),
                    fg="#4CAF50",
                )
                self._auth_label.pack()

            # ─── 按钮栏 ────────────────────────────────
            btn_frame = tk.Frame(self._root, padx=10, pady=10)
            btn_frame.pack(fill=tk.X)

            refresh_btn = tk.Button(
                btn_frame, text="🔄 刷新口令", command=self._handle_refresh,
                font=("Microsoft YaHei", 10), width=12,
            )
            refresh_btn.pack(side=tk.LEFT, padx=3)

            changepw_btn = tk.Button(
                btn_frame, text="🔑 修改密码", command=self._handle_change_password,
                font=("Microsoft YaHei", 10), width=12,
            )
            changepw_btn.pack(side=tk.LEFT, padx=3)

            resetpw_btn = tk.Button(
                btn_frame, text="🧩 重置密码", command=self._handle_reset_password,
                font=("Microsoft YaHei", 10), width=12,
            )
            resetpw_btn.pack(side=tk.LEFT, padx=3)

            quit_btn = tk.Button(
                btn_frame, text="❌ 退出", command=self._on_close,
                font=("Microsoft YaHei", 10), width=12, fg="red",
            )
            quit_btn.pack(side=tk.RIGHT, padx=3)

            # ─── 防火墙提示 ─────────────────────────────
            fw_frame = tk.Frame(self._root, padx=10, pady=5)
            fw_frame.pack(fill=tk.X)
            tk.Label(
                fw_frame,
                text="💡 若手机无法连接，请允许本程序通过 Windows Defender 防火墙（专用网络）。",
                font=("Microsoft YaHei", 8),
                fg="#999999",
                wraplength=380,
            ).pack()

            self._root.mainloop()

        except Exception as e:
            logger.error(f"QR 弹窗启动失败: {e}")
            logger.info(f"请手动访问: {self._url}")

    def _generate_qr_image(self) -> Image.Image:
        """生成二维码 PIL Image。"""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=2,
        )
        qr.add_data(self._url)
        qr.make(fit=True)
        return qr.make_image(fill_color="black", back_color="white").convert("RGB")

    def _refresh_display(self) -> None:
        """刷新二维码图片和 URL 显示。"""
        if self._url_var:
            self._url_var.set(self._url)

        img = self._generate_qr_image()
        self._photo = ImageTk.PhotoImage(img)
        if self._qr_label:
            self._qr_label.config(image=self._photo)

    def _copy_url(self) -> None:
        """复制 URL 到系统剪贴板。"""
        if self._root:
            self._root.clipboard_clear()
            self._root.clipboard_append(self._url)
            logger.info("URL 已复制到剪贴板")

    def _handle_refresh(self) -> None:
        """刷新 token 并更新二维码。"""
        if self._on_refresh:
            try:
                new_url = self._on_refresh()
                if new_url:
                    self._url = new_url
                    self._refresh_display()
                logger.info(f"Token 已刷新，新 URL 已更新")
            except Exception as e:
                logger.error(f"刷新 token 失败: {e}")

    def _handle_change_password(self) -> None:
        """弹出修改密码对话框。"""
        if self._on_change_password:
            try:
                ok = self._on_change_password(parent=self._root)
                if ok:
                    self._refresh_auth_label()
                    messagebox.showinfo(APP_NAME, "密码修改成功！", parent=self._root)
                else:
                    messagebox.showinfo(APP_NAME, "未修改密码。", parent=self._root)
            except Exception as e:
                logger.error(f"修改密码失败: {e}")

    def _handle_reset_password(self) -> None:
        """弹出重置密码对话框。"""
        if self._on_reset_password:
            try:
                ok = self._on_reset_password(parent=self._root)
                if ok:
                    self._refresh_auth_label()
                    messagebox.showinfo(APP_NAME, "账号密码已重置！", parent=self._root)
                else:
                    messagebox.showinfo(APP_NAME, "未重置账号密码。", parent=self._root)
            except Exception as e:
                logger.error(f"重置密码失败: {e}")

    def _refresh_auth_label(self) -> None:
        """刷新账号显示（用于修改/重置后更新）。"""
        if not self._auth_var or not self._auth_label:
            return
        new_username = None
        if self._get_auth_username:
            try:
                new_username = self._get_auth_username()
            except Exception:
                new_username = None
        if not new_username:
            new_username = self._auth_username
        if new_username:
            self._auth_var.set(f"👤 登录账号: {new_username}")

    def _on_close(self) -> None:
        """关闭窗口事件。"""
        if self._on_quit:
            self._on_quit()
        if self._root:
            self._root.destroy()
