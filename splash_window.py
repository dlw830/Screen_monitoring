"""
LanScreenMonitor V1 - 启动画面 (tkinter)
全屏科技感启动界面，包含联系方式。
必须在主线程中调用 show() / close()，以避免与其他 tkinter 窗口线程冲突。
"""

import math
import tkinter as tk
from typing import Optional

from config import APP_NAME, VERSION


class SplashWindow:
    """
    全屏科技感启动画面（主线程同步显示）：
    - 全屏深色背景 + 多层霓虹网格 + 扫描线动画 + 粒子装饰
    - 大字号标题居中，版本号和联系方式
    - 调用 show() 创建窗口并显示
    - 调用 close() 销毁窗口
    - 调用 update() 可在主线程做其他初始化时保持窗口刷新
    """

    def __init__(self):
        self._root: Optional[tk.Tk] = None
        self._canvas: Optional[tk.Canvas] = None
        self._scan_line_id: Optional[int] = None
        self._scan_line_id2: Optional[int] = None
        self._progress_id: Optional[int] = None
        self._status_id: Optional[int] = None
        self._glow_ids: list = []
        self._width = 0
        self._height = 0
        self._tick = 0

    def show(self) -> None:
        """在主线程中创建并显示全屏启动画面（非阻塞）。"""
        try:
            self._root = tk.Tk()
            self._root.title(APP_NAME)
            self._root.resizable(False, False)
            self._root.overrideredirect(True)
            self._root.attributes("-topmost", True)

            # 全屏
            W = self._root.winfo_screenwidth()
            H = self._root.winfo_screenheight()
            self._width, self._height = W, H
            self._root.geometry(f"{W}x{H}+0+0")

            c = tk.Canvas(self._root, width=W, height=H, highlightthickness=0)
            c.pack(fill=tk.BOTH, expand=True)
            self._canvas = c

            # ── 纯黑背景 ──
            c.create_rectangle(0, 0, W, H, fill="#050810", outline="")

            # ── 大网格（暗色底层） ──
            for x in range(0, W, 60):
                c.create_line(x, 0, x, H, fill="#0a1225", width=1)
            for y in range(0, H, 60):
                c.create_line(0, y, W, y, fill="#081020", width=1)

            # ── 中心辉光圆（多层渐变模拟） ──
            cx, cy = W // 2, H // 2 - 50
            for i, (radius, color) in enumerate([
                (220, "#061828"), (170, "#08203a"), (120, "#0a2a4e"),
                (80, "#0c3565"), (45, "#0e4080"),
            ]):
                c.create_oval(cx - radius, cy - radius, cx + radius, cy + radius,
                              fill=color, outline="")

            # ── 外层六边形（大） ──
            r_outer = 160
            pts_outer = []
            for i in range(6):
                angle = math.radians(60 * i - 30)
                pts_outer.extend([cx + r_outer * math.cos(angle), cy + r_outer * math.sin(angle)])
            c.create_polygon(pts_outer, outline="#00e5ff", fill="", width=3)

            # ── 中层六边形 ──
            r_mid = 115
            pts_mid = []
            for i in range(6):
                angle = math.radians(60 * i)
                pts_mid.extend([cx + r_mid * math.cos(angle), cy + r_mid * math.sin(angle)])
            c.create_polygon(pts_mid, outline="#0891b2", fill="", width=2)

            # ── 内层六边形 ──
            r_inner = 70
            pts_inner = []
            for i in range(6):
                angle = math.radians(60 * i + 15)
                pts_inner.extend([cx + r_inner * math.cos(angle), cy + r_inner * math.sin(angle)])
            c.create_polygon(pts_inner, outline="#06b6d4", fill="", width=1)

            # ── 放射线 ──
            for i in range(12):
                angle = math.radians(30 * i)
                x1 = cx + 50 * math.cos(angle)
                y1 = cy + 50 * math.sin(angle)
                x2 = cx + 200 * math.cos(angle)
                y2 = cy + 200 * math.sin(angle)
                c.create_line(x1, y1, x2, y2, fill="#0e2a47", width=1)

            # ── 中心光点 ──
            c.create_oval(cx - 8, cy - 8, cx + 8, cy + 8, fill="#00e5ff", outline="#00bcd4", width=2)

            # ── 角落装饰线 ──
            corner_len = 80
            corner_color = "#00e5ff"
            # 左上
            c.create_line(0, 0, corner_len, 0, fill=corner_color, width=3)
            c.create_line(0, 0, 0, corner_len, fill=corner_color, width=3)
            # 右上
            c.create_line(W, 0, W - corner_len, 0, fill=corner_color, width=3)
            c.create_line(W, 0, W, corner_len, fill=corner_color, width=3)
            # 左下
            c.create_line(0, H, corner_len, H, fill=corner_color, width=3)
            c.create_line(0, H, 0, H - corner_len, fill=corner_color, width=3)
            # 右下
            c.create_line(W, H, W - corner_len, H, fill=corner_color, width=3)
            c.create_line(W, H, W, H - corner_len, fill=corner_color, width=3)

            # ── 标题（居中大字） ──
            title_y = cy + 210
            c.create_text(cx, title_y, text="LanScreenMonitor",
                          fill="#00e5ff", font=("Consolas", 48, "bold"))
            # 版本徽章
            badge_y = title_y + 50
            bw = 120
            c.create_rectangle(cx - bw // 2, badge_y - 14, cx + bw // 2, badge_y + 14,
                               fill="#0e2a47", outline="#00bcd4", width=1)
            c.create_text(cx, badge_y, text=f"v{VERSION}",
                          fill="#7dd3fc", font=("Consolas", 14, "bold"))

            # ── 副标题 ──
            c.create_text(cx, badge_y + 45, text="零 配 置 局 域 网 屏 幕 监 控",
                          fill="#94a3b8", font=("Microsoft YaHei", 15))

            # ── 2 条扫描线（动画） ──
            self._scan_line_id = c.create_line(0, 0, W, 0, fill="#00e5ff", width=1)
            self._scan_line_id2 = c.create_line(0, H, W, H, fill="#0891b2", width=1)

            # ── 进度条 ──
            bar_y = H - 140
            bar_margin = 200
            c.create_rectangle(bar_margin, bar_y, W - bar_margin, bar_y + 8,
                               fill="#111827", outline="#1e3a5f")
            self._progress_id = c.create_rectangle(bar_margin, bar_y, bar_margin, bar_y + 8,
                                                    fill="#00e5ff", outline="")
            self._status_id = c.create_text(cx, bar_y + 30, text="正在初始化模块...",
                                            fill="#64748b", font=("Microsoft YaHei", 11))

            # ── 底部联系方式 ──
            footer_y = H - 55
            c.create_line(bar_margin, footer_y - 15, W - bar_margin, footer_y - 15,
                          fill="#1e293b", width=1)

            c.create_text(cx - 180, footer_y + 8, text="联系方式", fill="#a5b4fc",
                          font=("Microsoft YaHei", 11, "bold"), anchor="w")
            c.create_text(cx - 40, footer_y + 8, text="Email  1013344248@qq.com", fill="#cbd5e1",
                          font=("Consolas", 11), anchor="w")
            c.create_text(cx + 320, footer_y + 8, text="GitHub  @dlw830", fill="#cbd5e1",
                          font=("Consolas", 11), anchor="w")

            # ── 左右两侧装饰文字 ──
            c.create_text(30, H // 2, text="S Y S T E M", fill="#0e2a47",
                          font=("Consolas", 10), angle=90)
            c.create_text(W - 30, H // 2, text="M O N I T O R", fill="#0e2a47",
                          font=("Consolas", 10), angle=90)

            self._root.update()
        except Exception:
            self._root = None

    def update(self, status: str = "") -> None:
        """刷新窗口显示（主线程调用）。可选更新状态文字。"""
        if not self._root:
            return
        try:
            self._tick += 1
            c = self._canvas
            W, H = self._width, self._height

            # 扫描线动画（双向）
            y1 = (self._tick * 4) % H
            y2 = H - (self._tick * 3) % H
            c.coords(self._scan_line_id, 0, y1, W, y1)
            c.coords(self._scan_line_id2, 0, y2, W, y2)

            # 进度条动画
            bar_y = H - 140
            bar_margin = 200
            max_bar = W - 2 * bar_margin
            progress = min(self._tick * 5, max_bar)
            c.coords(self._progress_id, bar_margin, bar_y, bar_margin + progress, bar_y + 8)

            # 更新状态文字
            if status:
                c.itemconfigure(self._status_id, text=status)

            self._root.update()
        except Exception:
            pass

    def close(self) -> None:
        """销毁启动画面窗口。"""
        if self._root:
            try:
                self._root.destroy()
            except Exception:
                pass
            self._root = None
