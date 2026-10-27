"""主窗口：顶部蓝色标题栏（品牌 + 居中导航 + 账户） + 页面容器。"""

from __future__ import annotations

import queue
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont
from tkinter import messagebox, ttk

from .. import APP_NAME, __version__, accounts
from ..config import Config
from ..ui.theme import (
    ACCENT, ACCENT_DARK, ACCENT_HOVER, BG, BG_ALT, BG_HOVER, BORDER, DANGER, FG,
    FG_DIM, FG_FAINT, SUCCESS, WARN, FlatButton, apply_style, gradient, mix,
    round_rect,
)
from . import frameless, grab
from .widgets import Avatar, Toast


def _colorref(hex_color: str) -> int:
    """``#RRGGBB`` → Win32 COLORREF（0x00BBGGRR，注意是反的）。

    保留给主题/自定义描边等还需要 Win32 颜色的地方用；标题栏已经改成
    自绘无边框窗口（见 ``frameless.py``），不再靠 DWM 刷色。
    """
    h = (hex_color or "").lstrip("#")
    if len(h) != 6:
        return 0
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (b << 16) | (g << 8) | r


# 拖拽支持：tkinterdnd2 是可选的，缺了也不影响启动。
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    _DND_WRAPPER = TkinterDnD.DnDWrapper
except Exception:                                     # noqa: BLE001
    DND_FILES = None
    TkinterDnD = None
    _DND_WRAPPER = None

_BASES = (tk.Tk,) if _DND_WRAPPER is None else (tk.Tk, _DND_WRAPPER)

NAV_ITEMS = [
    ("home",    "开始",  "\u25b6"),
    ("install", "下载",  "\u2b07"),
    ("settings","设置",  "\u2692"),
]


class NavProxy:
    """``show_page`` 用的轻量代理：导航的真实绘制在 TopBar 上。"""

    def __init__(self, bar: "TopBar", key: str):
        self._bar = bar
        self.key = key

    def set_active(self, value: bool) -> None:
        if value:
            self._bar.set_active_key(self.key)


class TopBar(tk.Canvas):
    """PCL 风格顶栏：蓝色横向渐变 + 品牌 + 居中导航 + 账户胶囊 + 窗口按钮。

    原生标题栏已经被 ``frameless.apply`` 摘掉了，所以这一条就是窗口最顶上那
    行：右边画出最小化 / 最大化 / 关闭，用户反馈的「标题栏和顶栏分成两条」
    不再存在。拖动由 ``frameless.begin_drag`` 把 ``HTCAPTION`` 交回系统处理，
    贴边吸附、拖到顶部最大化、双击最大化都还是系统行为。
    """

    H = 48
    BTN_W = 46                       # 单个窗口按钮宽度，三个共 138
    DBL_MS = 420                     # 双击判定窗口
    DBL_PX = 4                       # 双击允许的鼠标移动

    def __init__(self, master, app):
        super().__init__(master, height=self.H, highlightthickness=0, bd=0,
                         bg=ACCENT_DARK)
        self.app = app
        self._bar_w = 1040
        self._active = ""
        self._hover = ""
        self._name = ""
        self._sub = ""
        self._premium = False
        self._nav_hits: list[tuple[str, float, float]] = []
        self._acc_hit: tuple[float, float] = (0, 0)
        self._btn_hits: list[tuple[str, float, float]] = []
        self._btn_hover = ""
        self._last_click = (0.0, 0, 0)

        self._f_nav = tkfont.Font(family="Microsoft YaHei UI", size=10)
        self._f_nav_b = tkfont.Font(family="Microsoft YaHei UI", size=10, weight="bold")
        self._f_brand = tkfont.Font(family="Segoe UI", size=12, weight="bold")
        self._f_small = tkfont.Font(family="Segoe UI", size=8)
        self._f_logo = tkfont.Font(family="Segoe UI", size=14, weight="bold")

        self.avatar = Avatar(self, size=26, bg=mix(ACCENT_HOVER, "#FFFFFF", 0.14))
        self.bind("<Configure>", self._on_configure)
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", lambda _e: self._set_hover(""))
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_motion)
        self.bind("<ButtonRelease-1>", self._on_release)
        self._pending_drag = False
        self._drag_origin = (0, 0)
        self._draw()

    # ---------------------------------------------------------- 事件

    def _on_configure(self, event) -> None:
        if event.width > 100 and event.width != self._bar_w:
            self._bar_w = event.width
            self._draw()

    def _sync_size_and_draw(self) -> None:
        """按控件真实宽度重画一次。

        ``_draw()`` 里画的是 ``self._bar_w``，而它只在 ``<Configure>`` 里更新；
        直接读一次真实宽度更保险（换主题重建、从最小化还原之后都可能有偏差）。
        """
        try:
            real = self.winfo_width()
        except tk.TclError:
            return
        if real > 100:
            self._bar_w = real
        self._draw()

    def _hit(self, x: float, y: float) -> str:
        if not (0 <= y <= self.H):
            return ""
        for key, x0, x1 in self._nav_hits:
            if x0 <= x <= x1:
                return key
        return ""

    def _hit_btn(self, x: float, y: float) -> str:
        for key, x0, x1 in self._btn_hits:
            if x0 <= x <= x1:
                return key
        return ""

    def _over_account(self, x: float, y: float) -> bool:
        x0, x1 = self._acc_hit
        return x0 <= x <= x1 and 0 <= y <= self.H

    def _on_motion(self, event) -> None:
        # 空白处按住后移动超过阈值 → 把拖动交给系统（贴边吸附免费）
        if self._pending_drag:
            dx = abs(event.x_root - self._drag_origin[0])
            dy = abs(event.y_root - self._drag_origin[1])
            if dx > self.DBL_PX or dy > self.DBL_PX:
                self._pending_drag = False
                frameless.begin_drag(self)
                return
        btn = self._hit_btn(event.x, event.y)
        if btn != self._btn_hover:
            self._btn_hover = btn
            self._draw()
        key = self._hit(event.x, event.y)
        if key != self._hover:
            self._hover = key
            self._draw()
        clickable = bool(btn or key or self._over_account(event.x, event.y))
        self.configure(cursor="hand2" if clickable else "")

    def _on_press(self, event) -> None:
        btn = self._hit_btn(event.x, event.y)
        if btn:
            self._pending_drag = False
            self._click_btn(btn)
            return
        key = self._hit(event.x, event.y)
        if key:
            self._pending_drag = False
            self.app.show_page(key)
            return
        if self._over_account(event.x, event.y):
            self._pending_drag = False
            self.app.open_account_tab()
            return
        # 空白处：先只记下起点。真的拖动起来再交给系统，否则按点击处理，
        # 这样双击最大化（连按两下、手不动）还能正常识别。
        self._pending_drag = True
        self._drag_origin = (event.x_root, event.y_root)

    def _on_release(self, event) -> None:
        if not self._pending_drag:
            return
        self._pending_drag = False
        now = time.monotonic()
        last_t, last_x, last_y = self._last_click
        near = abs(event.x_root - last_x) <= self.DBL_PX and \
            abs(event.y_root - last_y) <= self.DBL_PX
        if now - last_t <= self.DBL_MS / 1000.0 and near:
            self._last_click = (0.0, 0, 0)
            frameless.toggle_maximize(self)
            self.after(80, self._draw)
        else:
            self._last_click = (now, event.x_root, event.y_root)

    def _click_btn(self, key: str) -> None:
        if key == "min":
            frameless.minimize(self)
        elif key == "max":
            frameless.toggle_maximize(self)
            self.after(80, self._draw)
        elif key == "close":
            self.app.on_close()

    def _set_hover(self, key: str) -> None:
        if key != self._hover:
            self._hover = key
            self._draw()

    # ---------------------------------------------------------- 接口

    def set_active_key(self, key: str) -> None:
        self._active = key
        self._draw()

    def set_account(self, name: str, sub: str, premium: bool = False) -> None:
        self._name = name or ""
        self._sub = sub or ""
        self._premium = premium
        self.avatar.draw_letter(self._name or "?")
        self._draw()

    # ---------------------------------------------------------- 绘制

    def _draw(self) -> None:
        w, h = self._bar_w, self.H

        # 渐变有 160 条矩形，重铺一次要 ~2.4ms；顶栏宽度不变时只重画前景
        # （导航胶囊、账户胶囊），这是「切换页面卡」的主要来源。
        #
        # ⚠ 宽度变化时必须连前景一起清掉。原来这里只 delete("topbg")/
        # delete("topline")，前景的「M」「MCLite」「开始」「下载」「设置」「Steve」
        # 「▾」「✕」全部留在画布上，新前景又叠一层 —— 每改一次宽度就多攒 14 个
        # item，8 档之后同一串文字在画布上叠了 6 份。拉伸/拖动时那些旧 item 会
        # 落在窗口新露出的区域里，就是用户截图里那串错位重影（实测 175 → 245）。
        if getattr(self, "_bg_w", -1) != w:
            self.delete("all")
            self._bg_w = -1
        else:
            # 前景统一打 "fg" tag，hover 时删一次就够，不必遍历全部 item 比对 tags
            self.delete("fg")
        if self._bg_w != w:
            gradient(self, w, h, ACCENT_DARK, ACCENT_HOVER, steps=160, tag="topbg")
            self.create_line(0, h - 1, w, h - 1,
                             fill=mix(ACCENT_DARK, "#000000", 0.18), width=1,
                             tags="topline")
            self._bg_w = w

        cy = h / 2

        # ---- 品牌（版本号并到名字右边，省掉一行，顶栏可以矮一点）
        round_rect(self, 16, cy - 14, 44, cy + 14, 9, fill="#FFFFFF",
                   outline="#FFFFFF", tags="fg")
        self.create_text(30, cy, text="M", fill=ACCENT_DARK, font=self._f_logo,
                         tags="fg")
        self.create_text(52, cy, text=APP_NAME, anchor="w", fill="#FFFFFF",
                         font=self._f_brand, tags="fg")
        brand_right = 52 + self._f_brand.measure(APP_NAME) + 12

        # ---- 居中导航
        self._nav_hits = []
        widths: list[float] = []
        for _key, text, _icon in NAV_ITEMS:
            widths.append(max(76.0, self._f_nav_b.measure(text) + 44.0))
        gap = 6.0
        total = sum(widths) + gap * (len(widths) - 1)
        x = max(brand_right, (w - total) / 2)
        for (key, text, _icon), pw in zip(NAV_ITEMS, widths):
            active = key == self._active
            hover = key == self._hover and not active
            if active:
                fill, fg = "#FFFFFF", ACCENT_DARK
            elif hover:
                fill, fg = mix(ACCENT_HOVER, "#FFFFFF", 0.20), "#FFFFFF"
            else:
                fill, fg = "", "#D6E6FA"
            if fill:
                round_rect(self, x, cy - 15, x + pw, cy + 15, 15, fill=fill,
                           outline=fill, tags="fg")
            self.create_text(x + pw / 2, cy, text=text, fill=fg,
                             font=self._f_nav_b if active else self._f_nav,
                             tags="fg")
            self._nav_hits.append((key, x, x + pw))
            x += pw + gap

        # ---- 右侧账户胶囊（让出最右边三个窗口按钮的位置）
        chip_fill = mix(ACCENT_HOVER, "#FFFFFF", 0.14)
        name_w = float(self._f_nav_b.measure(self._name or "Steve"))
        chip_w = 10 + 26 + 8 + name_w + 22
        btn_zone = self.BTN_W * 3
        x1 = w - btn_zone - 8
        x0 = x1 - chip_w
        self._acc_hit = (x0, x1)
        if x0 > brand_right:
            round_rect(self, x0, cy - 14, x1, cy + 14, 14, fill=chip_fill,
                       outline=chip_fill, tags="fg")
            self.avatar.configure(bg=chip_fill)
            self.create_window(x0 + 9, cy, window=self.avatar, anchor="w", tags="fg")
            self.create_text(x0 + 9 + 34, cy, text=self._name or "Steve", anchor="w",
                             fill="#FFFFFF", font=self._f_nav_b, tags="fg")
            self.create_text(x1 - 11, cy, text="\u25be",
                             fill=mix("#FFFFFF", ACCENT_DARK, 0.25), font=self._f_small,
                             tags="fg")
        else:
            self._acc_hit = (0, 0)

        # ---- 最右：最小化 / 最大化 / 关闭（并进顶栏，取代原生标题栏）
        self._draw_window_buttons(w, h, cy)

    def _draw_window_buttons(self, w: int, h: int, cy: float) -> None:
        """三个窗口按钮：46px 宽、整条顶栏高，hover 亮一档，关闭按钮 hover 变红。"""
        self._btn_hits = []
        zoomed = frameless.is_maximized(self)
        specs = (("min", "\u2500"), ("max", "\u25a1"), ("close", "\u2715"))
        x = w - self.BTN_W * len(specs)
        for key, glyph in specs:
            x0, x1 = x, x + self.BTN_W
            hover = key == self._btn_hover
            if hover:
                fill = mix(ACCENT_DARK, "#D13438" if key == "close" else "#FFFFFF",
                           0.55 if key == "close" else 0.16)
                self.create_rectangle(x0, 0, x1, h, fill=fill, outline=fill,
                                      tags="fg")
            fg = "#FFFFFF"
            # 最大化/还原共用一个按钮位：系统处于最大化时画「还原」的双框
            if key == "max" and zoomed:
                self.create_rectangle(x1 - self.BTN_W / 2 - 6,
                                      cy - 5, x1 - self.BTN_W / 2 + 5, cy + 5,
                                      outline=fg, width=1, tags="fg")
                self.create_rectangle(x1 - self.BTN_W / 2 - 4,
                                      cy - 7, x1 - self.BTN_W / 2 + 7, cy + 3,
                                      outline=fg, width=1, tags="fg")
            elif key == "max":
                self.create_rectangle(x1 - self.BTN_W / 2 - 5,
                                      cy - 5, x1 - self.BTN_W / 2 + 5, cy + 5,
                                      outline=fg, width=1, tags="fg")
            elif key == "close":
                self.create_text((x0 + x1) / 2, cy, text=glyph, fill=fg,
                                 font=self._f_small, tags="fg")
            else:
                self.create_line(x0 + self.BTN_W / 2 - 5, cy, x1 - self.BTN_W / 2 + 5, cy,
                                 fill=fg, width=1, tags="fg")
            self._btn_hits.append((key, x0, x1))
            x = x1


class App(*_BASES):
    def __init__(self) -> None:
        super().__init__()
        self.cfg = Config()
        self.fonts = apply_style(self)
        self._accounts = accounts.load(self.cfg)
        if not self._accounts and self.cfg.get("username"):
            self._accounts = [accounts.Account.new_offline(str(self.cfg.get("username")))]
            self.cfg.set("current_account", 0)

        self._dnd_ok = False
        self._dnd_registered: set[str] = set()
        if _DND_WRAPPER is not None:
            try:
                TkinterDnD._require(self)
                self._dnd_ok = True
            except Exception:                         # noqa: BLE001
                self._dnd_ok = False

        self.title(f"{APP_NAME}  {__version__}")
        self.geometry("1160x724")
        self._set_icon()
        self.minsize(880, 560)
        self.configure(bg=BG)
        self._center()

        try:
            self.iconbitmap(default="")
        except tk.TclError:
            pass

        self._pages: dict[str, tk.Frame] = {}
        self._nav: dict[str, NavButton] = {}
        self._current = ""
        self._running_task = False
        self._main_queue: queue.Queue = queue.Queue()

        self._build()
        self.show_page("home")
        self._drain_queue()

    # ------------------------------------------------------------ 跨线程
    def post(self, fn) -> None:
        """从任意线程把回调排到主线程。"""
        self._main_queue.put(fn)

    def _drain_queue(self) -> None:
        for _ in range(64):
            try:
                fn = self._main_queue.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception:                        # noqa: BLE001
                pass
        try:
            self.after(40, self._drain_queue)
        except tk.TclError:
            pass

    # ------------------------------------------------------------ 布局

    def _center(self) -> None:
        self.update_idletasks()
        w, h = 1160, 724
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2 - 20)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build(self) -> None:
        # 换主题后就地重建，ttk 样式与字体得跟着当前颜色重新生成
        self.fonts = apply_style(self)
        self.configure(bg=BG)

        # ---------------- 顶部蓝色渐变栏（已取代原生标题栏，见 frameless）
        self._topbar = TopBar(self, self)
        self._topbar.pack(side="top", fill="x", ipady=0)
        self._apply_frameless()

        body = tk.Frame(self, bg=BG)
        body.pack(side="top", fill="both", expand=True)

        # ---------------- 左侧：账户卡（含皮肤入口）
        self._side = tk.Frame(body, bg=BG_ALT, width=232)
        self._side.pack(side="left", fill="y")
        self._side.pack_propagate(False)
        tk.Frame(body, bg=BORDER, width=1).pack(side="left", fill="y")

        self._account_frame = tk.Frame(self._side, bg=BG_ALT)
        self._account_frame.pack(fill="x", pady=(16, 0), padx=14)
        self._build_account()

        # ---------------- 右侧：页面容器（不再有底部状态栏：
        # 用户反馈「这边也可以扔了」，消息统一走右上角的 Toast）
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True)

        self._container = tk.Frame(right, bg=BG)
        self._container.pack(fill="both", expand=True)
        # 页面用「像素尺寸 + 节流」的方式跟随容器，而不是 relwidth=1：
        # relwidth 会让 Tk 在窗口拉伸的每一帧都重排当前页（实测 home 页 75ms/帧，
        # 用户反馈「页面拉伸的时候很卡」）。改成拖边框时不跟着重排、停手 70ms 后
        # 一次性对齐（53ms 且只发生一次），拖动过程中手感立刻跟手。
        # 拉伸期间还会冻结整窗重绘（见 _on_container_configure），那一步才是
        # 把 190ms/帧压到 3.3ms 的关键。
        self._page_sync_job = None
        self._cont_size = (0, 0)
        # 拉伸期间顶替页面的「像素快照」（见 _snapshot_page），None = 没有快照
        self._snap = None
        self._snap_ok = True
        # 连续 Configure 计数 + 上次到来的时刻：用来区分「用户正在拖边框」
        # （连着一串 Configure）和「最大化/还原/一次性的尺寸跳变」（一个就没了）。
        # 拍快照要 155–170 ms，只有前者值得付。
        self._cfg_count = 0
        self._cfg_last = 0.0
        self._container.bind("<Configure>", self._on_container_configure)

        self.toast = Toast(self)
        self._refresh_topbar()

    # ------------------------------------------------------------ 无边框窗口

    def _apply_frameless(self) -> None:
        """摘掉原生标题栏，让顶栏成为窗口最顶上一行。

        必须在窗口已经映射之后再改样式（``winfo_id`` 才有真实 hwnd），所以
        第一次调用延后到 idle；换主题重建界面时窗口已经无边框，重复调用会
        在 ``frameless.apply`` 里看到没有 ``WS_CAPTION`` 后直接返回。

        ⚠ 不要在顶层窗口上绑 ``<Map>``：去 caption 之后 Map 会在映射过程中
        反复触发，回调里再去改画布会把 Tk 拖进重入（实测表现为
        0xC0000005 直接崩进程）。顶栏上的最大化/还原图标由 ``TopBar`` 自己
        的 ``<Configure>`` 重画——最大化时宽度必然变化，够用了。
        """
        def run() -> None:
            try:
                # 顶栏渐变从 ACCENT_DARK 起，所以窗口最顶上那条非客户区边
                # （摘掉 caption 后露出的 7px 缩放边框）也用同一个色，
                # 否则蓝顶栏上面会挂一条 #F3F3F3 灰边。
                frameless.apply(self, caption_color=ACCENT_DARK)
            except Exception:                        # noqa: BLE001
                pass
            bar = getattr(self, "_topbar", None)
            if bar is not None:
                try:
                    bar._draw()
                except tk.TclError:
                    pass

        self.after_idle(run)

    def _sync_window_buttons(self) -> None:
        bar = getattr(self, "_topbar", None)
        if bar is None:
            return
        try:
            bar._draw()
        except tk.TclError:
            pass

    def _refresh_topbar(self) -> None:
        acc = self.current_account()
        name = acc.name if acc else (self.cfg.get("username") or "Steve")
        premium = acc is not None and acc.premium
        if premium:
            sub = "微软正版账户"
        elif acc is not None and acc.third_party:
            sub = acc.site_name or "第三方账户"
        else:
            sub = "离线账户"
        bar = getattr(self, "_topbar", None)
        if bar is not None:
            bar.set_account(name, sub, premium)
            bar.set_active_key(self._current or "home")
            self._load_avatar(bar.avatar, acc)

    def _build_account(self) -> None:
        """左侧白栏的账户卡：头像 + 名字 + 皮肤入口并成一栏。

        用户反馈「这些选项的排版不太好，皮肤可以和账号选项拼在一起」——
        原来下面还挂着游戏目录 / 版本设置 / 皮肤管理三行文字，和顶栏、页签
        里的入口重复了三遍；现在只留账户本身，皮肤做成同一条里的按钮，
        游戏目录改由页面里的路径标签直接打开。
        """
        for w in self._account_frame.winfo_children():
            w.destroy()

        acc = self.current_account()
        name = acc.name if acc else (self.cfg.get("username") or "Steve")
        premium = acc is not None and acc.premium
        if premium:
            subtitle = "微软正版账户"
        elif acc is not None and acc.third_party:
            subtitle = acc.site_name or "第三方账户"
        else:
            subtitle = "离线账户"

        card = tk.Frame(self._account_frame, bg=BG_ALT)
        card.pack(fill="x")

        top = tk.Frame(card, bg=BG_ALT)
        top.pack(fill="x")

        avatar = Avatar(top, size=52, bg=BG_ALT, border=BG_HOVER)
        avatar.pack(side="left", pady=2)

        box = tk.Frame(top, bg=BG_ALT, cursor="hand2")
        box.pack(side="left", fill="x", expand=True, padx=(10, 0))
        lbl1 = tk.Label(box, text=name, bg=BG_ALT, fg=FG, anchor="w",
                        font=self.fonts["h2"], cursor="hand2")
        lbl1.pack(fill="x")
        lbl2 = tk.Label(box, text=subtitle, bg=BG_ALT,
                        fg=ACCENT if premium else FG_FAINT, anchor="w",
                        font=self.fonts["small"], cursor="hand2")
        lbl2.pack(fill="x", pady=(1, 0))

        # 点头像或名字 = 进账户页签（不再额外放一行「账户管理」文字）
        for w in (top, box, avatar, lbl1, lbl2):
            w.bind("<Button-1>", lambda _e: self.open_accounts())
        for w in (box, lbl1, lbl2):
            w.bind("<Enter>", lambda _e: lbl1.configure(fg=ACCENT))
            w.bind("<Leave>", lambda _e: lbl1.configure(fg=FG))

        # ---- 账户 / 皮肤：并排一条，取代原来竖着的三行入口
        acts = tk.Frame(card, bg=BG_ALT)
        acts.pack(fill="x", pady=(12, 2))
        FlatButton(acts, "账户", command=self.open_accounts, kind="ghost",
                   height=28, width=84, font=self.fonts["small"],
                   bg=BG_ALT).pack(side="left")
        FlatButton(acts, "皮肤", command=self.open_skin_manager, kind="ghost",
                   height=28, width=84, font=self.fonts["small"],
                   bg=BG_ALT).pack(side="left", padx=(8, 0))

    def _open_game_dir(self) -> None:
        import os
        import subprocess

        path = self.cfg.game_dir
        try:
            path.mkdir(parents=True, exist_ok=True)
            os.startfile(str(path))
        except Exception:                              # noqa: BLE001
            subprocess.Popen(["explorer", str(path)])

    def _load_avatar(self, avatar, acc) -> None:
        """侧边栏头像：先用首字母，再后台拉真实皮肤的头像。"""
        import threading

        from .. import skins

        name = acc.name if acc is not None else str(self.cfg.get("username") or "Steve")
        avatar.draw_letter(name)
        if acc is None or not acc.uuid:
            return
        api = acc.api if acc.third_party else ""
        uuid = acc.uuid.replace("-", "")

        def work() -> None:
            png = skins.fetch_skin_png(uuid, api)
            if not png:
                return

            def apply() -> None:
                try:
                    avatar.draw_skin(png)
                except tk.TclError:
                    pass

            self.post(apply)

        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------ 账户

    @property
    def accounts(self) -> list:
        return self._accounts

    def current_account(self):
        idx = accounts.current_index(self.cfg, len(self._accounts))
        return self._accounts[idx] if idx >= 0 else None

    @property
    def ms_account(self):
        acc = self.current_account()
        if acc is not None and acc.premium and acc.refresh_token:
            return acc.to_ms()
        return None

    def effective_account(self) -> tuple[str, str, str, str]:
        """启动时用哪个账号：返回 (名字, uuid, access_token, user_type)。"""
        acc = self.current_account()
        if acc is not None and acc.premium and acc.access_token:
            return acc.name, acc.uuid, acc.access_token, "msa"
        if acc is not None and acc.third_party and acc.access_token:
            return acc.name, acc.uuid, acc.access_token, "legacy"
        if acc is not None and acc.kind == "offline":
            uuid = acc.uuid or accounts.offline_uuid(acc.name)
            return acc.name, uuid, "0", "legacy"
        name = str(self.cfg.get("username") or "Steve")
        return name, accounts.offline_uuid(name), "0", "legacy"

    @property
    def skin_account(self):
        """当前账号如果是第三方皮肤站账号，返回可直接用于注入的 SkinAccount。"""
        acc = self.current_account()
        if acc is None or not acc.third_party or not acc.access_token or not acc.api:
            return None
        from ..skin_sites import SkinAccount
        return SkinAccount(name=acc.name, uuid=acc.uuid, access_token=acc.access_token,
                           api=acc.api, site_id=acc.site_id, client_token=acc.client_token)

    def set_skin_account(self, skin, make_current: bool = True) -> None:
        from ..accounts import Account
        self._accounts, idx = accounts.upsert(self._accounts, Account.from_skin(skin),
                                              make_current=make_current)
        accounts.save(self.cfg, self._accounts, idx)
        self.cfg.set("username", skin.name)
        self.cfg.save()
        self.refresh_account()
        self._notify_home()

    def open_skin_login(self) -> None:
        from .skin_dialog import SkinLoginDialog
        dlg = SkinLoginDialog(self, on_done=self.set_skin_account)
        try:
            dlg.grab_set()
        except tk.TclError:
            pass

    def set_ms_account(self, account) -> None:
        from ..accounts import Account
        self._accounts, idx = accounts.upsert(self._accounts, Account.from_ms(account))
        accounts.save(self.cfg, self._accounts, idx)
        self.cfg.set("username", account.name)
        self.cfg.save()
        self.refresh_account()
        self._notify_home()

    def switch_account(self, index: int) -> None:
        if not (0 <= index < len(self._accounts)):
            return
        accounts.save(self.cfg, self._accounts, index)
        acc = self._accounts[index]
        self.cfg.set("username", acc.name)
        self.cfg.save()
        self.refresh_account()
        self._notify_home()

    def add_offline_account(self, name: str):
        from ..accounts import Account
        name = (name or "").strip() or "Steve"
        self._accounts, idx = accounts.upsert(self._accounts, Account.new_offline(name))
        accounts.save(self.cfg, self._accounts, idx)
        self.cfg.set("username", name)
        self.cfg.save()
        self.refresh_account()
        self._notify_home()
        return self._accounts[idx]

    def remove_account(self, index: int) -> None:
        self._accounts, idx = accounts.remove(self._accounts, index)
        accounts.save(self.cfg, self._accounts, idx)
        self.refresh_account()
        self._notify_home()

    def _notify_home(self) -> None:
        page = self._pages.get("home")
        if page is not None and hasattr(page, "on_account_changed"):
            try:
                page.on_account_changed()
            except Exception:                        # noqa: BLE001
                pass

    def open_login(self) -> None:
        from .ms_login import MsLoginDialog
        dlg = MsLoginDialog(self)
        try:
            dlg.grab_set()
        except tk.TclError:
            pass

    # -- 内嵌页签入口（账户管理 / 模组管理不再单开页面或弹窗）

    def open_account_tab(self) -> None:
        """切到开始页的「账户」页签。"""
        self.show_page("home")
        page = self._pages.get("home")
        if page is not None and hasattr(page, "show_tab"):
            try:
                page.show_tab("account")
            except Exception:                        # noqa: BLE001
                pass

    def open_mods_tab(self) -> None:
        """切到开始页的「模组」页签。"""
        self.show_page("home")
        page = self._pages.get("home")
        if page is not None and hasattr(page, "show_tab"):
            try:
                page.show_tab("mods")
            except Exception:                        # noqa: BLE001
                pass

    def open_accounts(self) -> None:
        """兼容旧调用点：现在等价于切到账户页签。"""
        self.open_account_tab()

    def open_skin_manager(self) -> None:
        from .skin_mgr_dialog import SkinDialog
        dlg = SkinDialog(self)
        try:
            dlg.grab_set()
        except tk.TclError:
            pass

    # ------------------------------------------------------------ 图标

    def _set_icon(self) -> None:
        import sys
        from pathlib import Path
        candidates: list[Path] = []
        base = getattr(sys, "_MEIPASS", None)
        if base:
            candidates.append(Path(base) / "assets" / "icon.ico")
        here = Path(__file__).resolve().parent.parent.parent
        candidates.append(here / "assets" / "icon.ico")
        if getattr(sys, "frozen", False):
            candidates.append(Path(sys.executable))
        for c in candidates:
            try:
                if c.is_file():
                    self.iconbitmap(str(c))
                    return
            except (tk.TclError, OSError):
                continue

    # ------------------------------------------------------------ 页面

    def create_pages(self) -> None:
        """建立三个页面。换主题重建界面时会再次调用。"""
        from .page_home import HomePage
        from .page_install import InstallPage
        from .page_settings import SettingsPage

        self.register_page("home", HomePage(self._container, self))
        self.register_page("install", InstallPage(self._container, self))
        self.register_page("settings", SettingsPage(self._container, self))
        self.after(200, self._setup_dnd)

    # ------------------------------------------------------------ 拖拽

    def _setup_dnd(self) -> None:
        if not self._dnd_ok:
            return
        self.add_drop_target(self)
        self.add_drop_target(self._container)

    def add_drop_target(self, widget) -> None:
        """把 widget 及其所有子控件注册成投放目标。

        按 Tk 控件路径去重：页面上百个列表行，每次切页都重新注册一遍要 200+
        毫秒（用户反馈的"切换页面比较卡"主要就是这个）。已注册过的路径直接
        跳过整棵子树 —— 同一趟遍历里父子是一起登记的，父路径已登记就意味着
        底下每个控件也都登记过了。控件被销毁后重建往往复用同一路径，那时它
        本来就是合法投放目标，不需要再登记一次。
        """
        if not self._dnd_ok or _DND_WRAPPER is None:
            return
        stack = [widget]
        while stack:
            w = stack.pop()
            try:
                path = str(w)
            except tk.TclError:
                continue
            if path in self._dnd_registered:
                continue
            try:
                _DND_WRAPPER.drop_target_register(w, DND_FILES)
                _DND_WRAPPER.dnd_bind(w, "<<Drop>>", self._on_drop)
                self._dnd_registered.add(path)
            except Exception:                 # noqa: BLE001
                pass
            try:
                stack.extend(w.winfo_children())
            except tk.TclError:
                pass

    def _on_drop(self, event):
        try:
            paths = [Path(p) for p in self.tk.splitlist(event.data)]
        except (tk.TclError, ValueError):
            paths = [Path(str(event.data))]
        self.handle_drop(paths)
        return "copy"

    def handle_drop(self, paths: list[Path]) -> None:
        """拖入文件的统一入口：先给当前页处理，不行就交给模组页签。"""
        paths = [p for p in paths if p]
        if not paths:
            return
        page = self._pages.get(self._current)
        if page is not None and hasattr(page, "handle_drop"):
            try:
                page.handle_drop(paths)
                return
            except Exception as exc:              # noqa: BLE001
                self.notify(f"处理拖入文件失败：{exc}", "err")
                return
        home = self._pages.get("home")
        if home is not None and hasattr(home, "handle_drop"):
            try:
                home.handle_drop(paths)
                return
            except Exception:                     # noqa: BLE001
                pass
        self.notify("这个页面不支持拖入文件", "warn")

    def register_page(self, key: str, page: tk.Frame) -> None:
        self._pages[key] = page

    # ------------------------------------------------------------ 页面尺寸

    def _on_container_configure(self, event) -> None:
        """容器尺寸变了：拖动期间用「像素快照」顶替页面，停手后一次性重排。

        纯用像素尺寸 + 节流（v1.7.2 的做法）能把手感从 95.8ms/帧降到 40ms/帧，
        但拖动中 Windows 每一帧都要重画页面里那几百个子窗口，仍然肉眼可见地
        拖影。这里改成：**拖动一开始就给页面拍一张照片，页面本身 place_forget，
        画布盖上照片**；照片按原尺寸贴在容器左上角、不缩放（窗口变小就裁掉，
        变大就露出容器底色），每一帧的成本只剩「画一张图」的 ~25ms。停手后销毁
        照片、按最终尺寸把真页面摆回来 —— 用户看不到跳变，因为照片内容就是真
        页面停手那一刻的样子。实测 95.8ms/帧 → 28ms/帧，且画面完整无拉伸。

        ⚠ **不要再用 ``frameless.freeze``（LockWindowUpdate + WM_SETREDRAW）
        来「冻结画面」**。它确实能把拖动帧压到 3ms，但代价是画面坏掉：Windows
        在这期间会把最后一帧**拉伸**铺满新窗口，用户看到一整条被拉长的顶栏和糊
        成一团的文字，解冻后正文还常常整片空白（``RedrawWindow`` +
        ``RDW_ALLCHILDREN`` 补不回来 Tk 子窗口）。用户报的「拖动时出现残影」
        就是这个，v1.7.1 加的东西，v1.7.3 全部拆掉。
        """
        if (event.width, event.height) == self._cont_size:
            return
        self._cont_size = (event.width, event.height)

        # 区分「正在拖边框」和「一次性的尺寸跳变」：拖动时 <Configure> 会以
        # 几十毫秒的间隔连成一串；最大化、还原、换页只有孤零零一个。
        now = time.monotonic()
        self._cfg_count = self._cfg_count + 1 if now - self._cfg_last < 0.30 else 1
        self._cfg_last = now
        # 第一个 Configure 不拍快照：单次跳变（最大化/还原/首帧）拍了就是白花
        # 155–170 ms（实测 install 收尾那 100 ms 的一帧全是它）。第二个到来
        # 才说明用户真的在拖，那时才盖照片。
        if self._cfg_count >= 2:
            self._ensure_snapshot()

        if self._page_sync_job is not None:
            try:
                self.after_cancel(self._page_sync_job)
            except tk.TclError:
                pass
        # 70ms 真防抖：每次 Configure 都重置，所以只有停手后才会真正重排一次。
        self._page_sync_job = self.after(70, self._flush_page_size)

    def _ensure_snapshot(self) -> None:
        """拖动开始时给当前页面拍一张照片盖上去（每轮拖动只拍一次）。"""
        if self._snap is not None or not self._snap_ok:
            return
        if not grab.available():
            self._snap_ok = False
            return
        page = self._pages.get(self._current)
        if page is None:
            return
        try:
            if not page.winfo_ismapped():
                return
            x, y = page.winfo_rootx(), page.winfo_rooty()
            w, h = page.winfo_width(), page.winfo_height()
        except tk.TclError:
            return
        if w <= 1 or h <= 1:
            return
        # 抓的是屏幕上这一页真实像素。窗口刚被拉过一帧的话照片会带上旧位置，
        # 但照片只在一个拖动过程里用 ~200ms，用户看不出来。
        ppm = grab.grab_ppm(x, y, w, h)
        if ppm is None:
            self._snap_ok = False
            return
        try:
            photo = tk.PhotoImage(master=self, data=ppm, format="ppm")
            cv = tk.Canvas(self._container, bg=BG, highlightthickness=0, bd=0)
            cv.create_image(0, 0, image=photo, anchor="nw")
            cv.place(x=0, y=0, width=w, height=h)
            page.place_forget()
        except tk.TclError:
            self._snap_ok = False
            return
        self._snap = (cv, photo)
        # 抓图 + 建图 ~19ms 已经吃掉一帧，把防抖往后推一点，别刚拍完就重排。
        if self._page_sync_job is not None:
            try:
                self.after_cancel(self._page_sync_job)
            except tk.TclError:
                pass
        self._page_sync_job = self.after(70, self._flush_page_size)

    def _drop_snapshot(self) -> None:
        """销毁快照画布，交还真实页面（真页面由 _place_page 重新摆）。"""
        if self._snap is None:
            return
        cv, photo = self._snap
        self._snap = None
        try:
            cv.destroy()
        except tk.TclError:
            pass
        # PhotoImage 的 __del__ 会自己 image delete；这里显式释放是为了不等 GC
        # （一张 929x676 的图约 2.5MB），同时避免 Tk 里残留无名图片。
        try:
            photo.__del__()                      # noqa: PLC2801
        except Exception:                        # noqa: BLE001
            pass

    def _flush_page_size(self) -> None:
        self._page_sync_job = None
        w, h = self._cont_size
        if w <= 1 or h <= 1:
            return
        page = self._pages.get(self._current)
        if page is None:
            return
        # 顺序关键：先摆真页面，再销毁快照。反过来的话照片撤掉那一帧会露出
        # 还没摆好的页面（用户看到一闪的空白）。
        self._place_page(page, w, h)
        self._drop_snapshot()
        # 页面拿到新宽度后通知它重排（收窄左栏、按钮行换行）。放在 place 之后：
        # 页面得先有真实宽度，各页面才量得准自己还剩多少空间。
        hook = getattr(page, "on_resize", None)
        if hook is not None:
            try:
                hook(w)
            except Exception:                        # noqa: BLE001
                pass

    def _place_page(self, page: tk.Frame, w: int, h: int) -> None:
        """把页面按**绝对像素**铺满容器。

        ⚠ 绝对尺寸和相对尺寸必须互斥：Tk 的 place 会把 ``relwidth`` 和
        ``width`` **相加**。启动早期容器还没实现（1x1），``show_page`` 走
        ``relwidth=1`` 分支；之后 ``_flush_page_size`` 再 ``place_configure(
        width=929)``，页面就变成 929(相对) + 929(绝对) = 1858 —— 正好两倍，
        右半部分的控件全被推到窗口外面，看起来就是「设置页卡死，只有切走再
        切回来才恢复」（切回来时重新 ``place`` 才把 relwidth 清掉）。
        所以这里每次都把 relwidth/relheight 显式清空。
        """
        try:
            page.place(x=0, y=0, width=w, height=h,
                       relwidth="", relheight="")
        except tk.TclError:
            pass

    def show_page(self, key: str) -> None:
        if key not in self._pages:
            return
        if self._current == key:
            return
        # 拖动中途切页（点导航）时先撤掉快照，否则新页面会被照片盖住。
        self._drop_snapshot()
        if self._current and self._current in self._pages:
            old = self._pages[self._current]
            if hasattr(old, "on_hide"):
                try:
                    old.on_hide()
                except Exception:                    # noqa: BLE001
                    pass

        page = self._pages[key]
        # 所有页面用 place 叠在同一个容器里。早先用 pack/pack_forget，每次切换
        # 都要重算整页几何：下载页 103 行约 620 个控件，单次要 390ms（用户反馈
        # 的"切换页面比较卡"）。place + lift 不动几何，切换降到几毫秒。
        #
        # 但**离开的页要 place_forget**：窗口拉伸时 Tk 会重排所有已 place 的
        # 页面，三个页面叠着一起算实测 154 ms，只留当前页 83 ms（用户反馈
        # "页面拉伸的时候很卡"）。恢复显示只是 place 一次，几毫秒。
        if self._current and self._current in self._pages and self._current != key:
            old_page = self._pages[self._current]
            try:
                old_page.place_forget()
            except tk.TclError:
                pass
        if not page.winfo_manager():
            w = self._container.winfo_width()
            h = self._container.winfo_height()
            if w > 1 and h > 1:
                self._cont_size = (w, h)
                self._place_page(page, w, h)
            else:
                # 容器还没实现（启动早期）：先按相对尺寸占位，等
                # _flush_page_size 拿到真实尺寸后用 _place_page 换掉。
                page.place(x=0, y=0, relwidth=1, relheight=1)
        page.lift()
        self._current = key
        bar = getattr(self, "_topbar", None)
        if bar is not None:
            bar.set_active_key(key)
        if hasattr(page, "on_show"):
            try:
                page.on_show()
            except Exception:                        # noqa: BLE001
                pass
        # 页面里的控件是 on_show 之后才建出来的，拖拽目标得重新登记一次
        if self._dnd_ok:
            self.after(60, lambda p=page: self.add_drop_target(p))
        # 切到一页时也重排一次：新建的页面要按当前宽度把左栏/按钮行摆好，
        # 否则它会以设计宽度（左栏 380）出现在窄窗口里。
        hook = getattr(page, "on_resize", None)
        if hook is not None:
            self.after(10, lambda: self._run_resize(page))

    def _run_resize(self, page: tk.Frame) -> None:
        """让页面按容器当前宽度重排一次（页面自己负责细节）。"""
        hook = getattr(page, "on_resize", None)
        if hook is None:
            return
        try:
            w = self._cont_size[0]
            if w <= 1:
                w = self._container.winfo_width()
            if w <= 1:
                return
            hook(w)
        except Exception:                            # noqa: BLE001
            pass

    def refresh_account(self) -> None:
        self._build_account()

    def notify_version_selected(self, version_id: str) -> None:
        """广播「开始页选中了哪个版本」，让下载页跟着换筛选条件。

        用户反馈「选了版本，右边面板没跟着变」：原来只有首页模组页签知道
        当前选中版本，下载页的 Mod 浏览器一直用启动时的旧上下文。这里统一
        通知一遍，各页面自己决定要不要用。
        """
        vid = str(version_id or "")
        for key, page in list(self._pages.items()):
            if key == "home":
                continue
            cb = getattr(page, "on_version_selected", None)
            if cb is None:
                continue
            try:
                cb(vid)
            except Exception:                        # noqa: BLE001
                pass
        self._refresh_topbar()

    # ------------------------------------------------------------ 状态提示

    def set_status(self, text: str, right: str = "") -> None:
        """兼容旧调用点：状态栏已经去掉，消息统一走右上角 Toast。

        空字符串表示「清掉提示」，不弹 Toast（原来用于复位成「就绪」）。
        """
        text = (text or "").strip()
        if not text or text == "就绪":
            return
        self.notify(text)

    def notify(self, text: str, kind: str = "info") -> None:
        try:
            self.toast.show(text, kind)
        except tk.TclError:
            pass

    # ------------------------------------------------------------ 主题

    def apply_theme(self, name: str) -> None:
        """切换配色并就地重建界面（不重启进程）。"""
        from . import theme as th

        name = th.set_theme(name)
        self.cfg.set("theme", name)
        self.cfg.save()
        try:
            self.configure(bg=BG)
        except tk.TclError:
            pass
        # 延后一帧：调用方可能正处在某个按钮的回调里，先让它安全返回
        self.after(30, self._rebuild)

    def _rebuild(self) -> None:
        current = self._current or "home"
        for w in self.winfo_children():
            try:
                w.destroy()
            except tk.TclError:
                pass
        self._pages.clear()
        self._nav.clear()
        self._current = ""
        self._build()
        self.create_pages()
        self.show_page(current if current in self._pages else "home")

    # ------------------------------------------------------------ 重启

    def restart(self) -> None:
        """关掉自己再起一个新进程。"""
        import subprocess
        import sys
        self.cfg.save()
        try:
            if getattr(sys, "frozen", False):
                subprocess.Popen([sys.executable], close_fds=True,
                                 creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
            else:
                entry = Path(__file__).resolve().parent.parent.parent / "main.py"
                subprocess.Popen([sys.executable, str(entry)], cwd=str(entry.parent),
                                 close_fds=True,
                                 creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
        except OSError as exc:
            messagebox.showerror("重启失败", f"请手动重新打开启动器。\n\n{exc}", parent=self)
            return
        self.destroy()

    # ------------------------------------------------------------ 关闭

    def on_close(self) -> None:
        if self._running_task:
            if not messagebox.askyesno("确认退出", "仍有任务在进行，确定要退出吗？", parent=self):
                return
        self.cfg.save()
        self.destroy()

