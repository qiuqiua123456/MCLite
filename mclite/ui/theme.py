"""PCL 风格主题：暗色 + 强调色、圆角按钮、扁平控件。

tkinter 原生控件很丑，这里用 Canvas 画圆角和自定义按钮，
其余用 ttk.Style 收敛成统一观感。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

# ---------------------------------------------------------------- 配色
#
# 主题在模块导入时按配置决定（配置值 theme）。因为各页面用
# ``from .theme import BG`` 取颜色，运行期改常量不会影响已建控件，
# 所以换主题后由界面提示「重启生效」——重启是一次完整的重新导入。

THEMES: dict[str, dict[str, str]] = {
    "pcl": {
        "label": "PCL 浅蓝",
        "bg":        "#EDF4FD",
        "bg_alt":    "#FFFFFF",
        "bg_hover":  "#E3EFFB",
        "bg_active": "#D2E4F8",
        "border":    "#DCE8F6",
        "fg":        "#16243A",
        "fg_dim":    "#5A7089",
        "fg_faint":  "#8598AD",
        "accent":      "#1277DD",
        "accent_dark": "#0E5FB8",
        "accent_hover": "#1B87E8",
        "success": "#1FA06A",
        "warn":    "#C9820F",
        "danger":  "#DE5548",
    },
    "dark": {
        "label": "暗色",
        "bg":        "#1e1f22",
        "bg_alt":    "#26272b",
        "bg_hover":  "#303136",
        "bg_active": "#383a40",
        "border":    "#3a3b40",
        "fg":        "#e6e6e6",
        "fg_dim":    "#9a9aa2",
        "fg_faint":  "#6b6b73",
        "accent":      "#3b8eea",
        "accent_dark": "#2f74c0",
        "accent_hover": "#4c9bf0",
        "success": "#4caf7d",
        "warn":    "#e0a33e",
        "danger":  "#e05a5a",
    },
    "light": {
        "label": "亮色",
        "bg":        "#f3f4f7",
        "bg_alt":    "#ffffff",
        "bg_hover":  "#e8ebf0",
        "bg_active": "#dce2ea",
        "border":    "#ccd2db",
        "fg":        "#20242b",
        "fg_dim":    "#5b636e",
        "fg_faint":  "#8b93a0",
        "accent":      "#2f7fdb",
        "accent_dark": "#2465b0",
        "accent_hover": "#3f90ec",
        "success": "#2e9e69",
        "warn":    "#c98314",
        "danger":  "#d4483f",
    },
    "midnight": {
        "label": "深蓝",
        "bg":        "#0f1520",
        "bg_alt":    "#17202e",
        "bg_hover":  "#1f2b3d",
        "bg_active": "#28374c",
        "border":    "#2b3b52",
        "fg":        "#dfe7f3",
        "fg_dim":    "#8b9bb4",
        "fg_faint":  "#5d6c84",
        "accent":      "#4a86e8",
        "accent_dark": "#3a6cc0",
        "accent_hover": "#5f96f2",
        "success": "#43b581",
        "warn":    "#e3b341",
        "danger":  "#e5645f",
    },
    "forest": {
        "label": "护眼绿",
        "bg":        "#1a231c",
        "bg_alt":    "#222e25",
        "bg_hover":  "#2a3a2e",
        "bg_active": "#33463a",
        "border":    "#37493c",
        "fg":        "#dfe9e0",
        "fg_dim":    "#96a899",
        "fg_faint":  "#6b7c6e",
        "accent":      "#3fa66a",
        "accent_dark": "#338a56",
        "accent_hover": "#4fbb7b",
        "success": "#4caf7d",
        "warn":    "#d9a840",
        "danger":  "#d9645a",
    },
}

THEME_ORDER = ["pcl", "dark", "light", "midnight", "forest"]
DEFAULT_THEME = "pcl"


def _active_theme_name() -> str:
    try:
        from ..config import Config   # 延迟导入，避免与 config 循环
        name = str(Config().get("theme") or DEFAULT_THEME)
    except Exception:                 # noqa: BLE001 - 任何异常都退回默认主题
        name = DEFAULT_THEME
    return name if name in THEMES else DEFAULT_THEME


THEME = _active_theme_name()
_P = THEMES[THEME]

BG          = _P["bg"]
BG_ALT      = _P["bg_alt"]
BG_HOVER    = _P["bg_hover"]
BG_ACTIVE   = _P["bg_active"]
BORDER      = _P["border"]
FG          = _P["fg"]
FG_DIM      = _P["fg_dim"]
FG_FAINT    = _P["fg_faint"]
ACCENT      = _P["accent"]
ACCENT_DARK = _P["accent_dark"]
ACCENT_HOVER= _P["accent_hover"]
SUCCESS     = _P["success"]
WARN        = _P["warn"]
DANGER      = _P["danger"]

FONT_FAMILY = "Microsoft YaHei UI"
FONT_MONO   = "Consolas"

#: 颜色常量名 → 主题字典里的键。换主题时按这份表逐个改名。
_COLOR_KEYS = {
    "BG": "bg", "BG_ALT": "bg_alt", "BG_HOVER": "bg_hover",
    "BG_ACTIVE": "bg_active", "BORDER": "border",
    "FG": "fg", "FG_DIM": "fg_dim", "FG_FAINT": "fg_faint",
    "ACCENT": "accent", "ACCENT_DARK": "accent_dark", "ACCENT_HOVER": "accent_hover",
    "SUCCESS": "success", "WARN": "warn", "DANGER": "danger",
}


def set_theme(name: str) -> str:
    """运行时切换配色（不重启）。

    难点：各页面用的是 `from .theme import BG`，导入时就把字符串绑死了，
    改 theme.BG 对它们无效。所以这里改完本模块的常量后，还要遍历已经
    导入的 mclite 模块，把同名常量逐个改掉；随后由 App 重建界面，
    新建的控件自然用上新颜色。
    """
    import sys

    global THEME, _P
    if name not in THEMES:
        name = DEFAULT_THEME
    THEME = name
    _P = THEMES[name]
    g = globals()
    for const, key in _COLOR_KEYS.items():
        g[const] = _P[key]
    for mod in list(sys.modules.values()):
        mod_name = getattr(mod, "__name__", "")
        if not mod_name.startswith("mclite"):
            continue
        for const in _COLOR_KEYS:
            if hasattr(mod, const):
                try:
                    setattr(mod, const, g[const])
                except Exception:              # noqa: BLE001 - 有的模块是只读属性
                    pass
        # THEME 也要跟着改：页面里 `from .theme import THEME` 用来判断
        # 当前选中的配色按钮，不改的话切完主题按钮还停在旧的那一个。
        if hasattr(mod, "THEME"):
            try:
                setattr(mod, "THEME", name)
            except Exception:                  # noqa: BLE001
                pass
    return name


def theme_label(name: str) -> str:
    return THEMES.get(name, THEMES[DEFAULT_THEME]).get("label", name)


def make_fonts() -> dict[str, tkfont.Font]:
    family = FONT_FAMILY
    try:
        available = set(tkfont.families())
        if family not in available:
            family = "Segoe UI" if "Segoe UI" in available else "TkDefaultFont"
    except tk.TclError:
        family = "TkDefaultFont"
    return {
        "h1":   tkfont.Font(family=family, size=17, weight="bold"),
        "h2":   tkfont.Font(family=family, size=12, weight="bold"),
        "body": tkfont.Font(family=family, size=9),
        "small": tkfont.Font(family=family, size=8),
        "mono": tkfont.Font(family=FONT_MONO, size=9),
        "btn":  tkfont.Font(family=family, size=9, weight="bold"),
    }


# ---------------------------------------------------------------- 圆角矩形

def hex_rgb(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def mix(c1: str, c2: str, t: float) -> str:
    """两个颜色按 t（0..1）线性插值。"""
    r1, g1, b1 = hex_rgb(c1)
    r2, g2, b2 = hex_rgb(c2)
    t = max(0.0, min(1.0, t))
    return "#%02x%02x%02x" % (round(r1 + (r2 - r1) * t),
                              round(g1 + (g2 - g1) * t),
                              round(b1 + (b2 - b1) * t))


def gradient(canvas: tk.Canvas, w: int, h: int, c1: str, c2: str,
             steps: int = 110, tag: str = "grad") -> None:
    """在 canvas 上横向铺一层两色渐变（Tk 没有原生渐变，用竖条拼接）。"""
    canvas.delete(tag)
    if w <= 0 or h <= 0:
        return
    steps = max(2, min(steps, max(2, w)))
    for i in range(steps):
        x0 = round(w * i / steps)
        x1 = round(w * (i + 1) / steps) + 1
        canvas.create_rectangle(x0, 0, x1, h, fill=mix(c1, c2, i / (steps - 1)),
                                outline="", tags=tag)


def round_rect(canvas: tk.Canvas, x1, y1, x2, y2, r=8, **kwargs):
    r = min(r, abs(x2 - x1) / 2, abs(y2 - y1) / 2)
    points = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


# ---------------------------------------------------------------- 控件

class FlatButton(tk.Canvas):
    """自绘圆角按钮，支持主色/普通/危险三种风格。"""

    def __init__(self, master, text: str, command=None, kind: str = "normal",
                 width: int | None = None, height: int = 32, radius: int = 6,
                 font=None, bg=None, **kwargs):
        self.kind = kind
        self._text = text
        self._command = command
        self._radius = radius
        self._enabled = True
        self._hover = False
        self._font = font or ("Microsoft YaHei UI", 9)
        f = tkfont.Font(font=self._font)
        w = width or (f.measure(text) + 34)
        super().__init__(master, width=w, height=height, highlightthickness=0,
                         bd=0, bg=bg or (master["bg"] if "bg" in master.keys() else BG), **kwargs)
        self._bw, self._bh = w, height
        self._draw()
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    # ---------------------------------------------------------- 颜色

    def _colors(self):
        if not self._enabled:
            return BG_HOVER, FG_FAINT, mix(BORDER, FG_FAINT, 0.25)
        if self.kind == "primary":
            fill = ACCENT_HOVER if self._hover else ACCENT
            return fill, "#ffffff", fill
        if self.kind == "accent_soft":
            # 浅色强调：用背景色把主色调淡，选中态在亮色主题下也不会变成一块暗色
            if self._hover:
                return mix(BG_ALT, ACCENT, 0.22), ACCENT_DARK, ACCENT
            return mix(BG_ALT, ACCENT, 0.13), ACCENT, mix(BG_ALT, ACCENT, 0.55)
        if self.kind == "danger":
            return (DANGER if self._hover else BG_ALT), (FG if not self._hover else "#ffffff"), (DANGER if self._hover else mix(BORDER, DANGER, 0.55))
        if self.kind == "ghost":
            return (BG_HOVER if self._hover else self["bg"]), FG_DIM, BG
        # normal：白底浅蓝描边，PCL 那两个「游戏目录 / 版本设置」按钮的观感
        return (BG_HOVER if self._hover else BG_ALT), FG, mix(BORDER, ACCENT, 0.30)

    def _draw(self):
        self.delete("all")
        fill, fg, outline = self._colors()
        round_rect(self, 1, 1, self._bw - 1, self._bh - 1, self._radius,
                   fill=fill, outline=outline if outline != fill else fill)
        self.create_text(self._bw / 2, self._bh / 2, text=self._text, fill=fg, font=self._font)

    # ---------------------------------------------------------- 事件

    def _on_enter(self, _e=None):
        if self._enabled:
            self._hover = True
            self._draw()
            self.configure(cursor="hand2")

    def _on_leave(self, _e=None):
        self._hover = False
        self._draw()
        self.configure(cursor="")

    def _on_press(self, _e=None):
        if self._enabled:
            self.configure(cursor="hand2")

    def _on_release(self, _e=None):
        if self._enabled and self._hover and self._command:
            self._command()

    # ---------------------------------------------------------- 接口

    def set_text(self, text: str):
        self._text = text
        self._draw()

    def set_enabled(self, value: bool):
        self._enabled = bool(value)
        self._hover = False
        self._draw()

    def set_size(self, width: int | None = None, height: int | None = None):
        """改按钮尺寸（窄窗口时把按钮收窄，否则会被挤到窗口外面）。

        宽度是画布尺寸而不是“按文字自适应”，所以必须显式改并重画。
        """
        if width is not None and int(width) != self._bw:
            self._bw = int(width)
            try:
                self.configure(width=self._bw)
            except tk.TclError:
                return
        if height is not None and int(height) != self._bh:
            self._bh = int(height)
            try:
                self.configure(height=self._bh)
            except tk.TclError:
                return
        self._draw()


class Slider(tk.Canvas):
    """自绘扁平滑块，替代外观糟糕的原生 tk.Scale。"""

    def __init__(self, master, from_: int, to: int, value: int, step: int = 1,
                 command=None, width: int = 220, height: int = 26,
                 bg: str | None = None, suffix: str = "", fmt=None):
        self._bg = bg or (master["bg"] if "bg" in master.keys() else BG)
        super().__init__(master, width=width, height=height, bg=self._bg,
                         highlightthickness=0, bd=0)
        self._min, self._max = from_, to
        self._step = max(1, step)
        self._value = self._clamp(value)
        self._command = command
        self._suffix = suffix
        self._fmt = fmt
        self._cw = width
        self._ch = height
        self._track_y = height - 8
        self._dragging = False
        self.bind("<Button-1>", self._on_click)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Configure>", self._on_resize)
        self._draw()

    def _on_resize(self, event) -> None:
        if event.width > 10 and event.width != self._cw:
            self._cw = event.width
            self._draw()

    # ---------------------------------------------------------- 数值

    def _clamp(self, v) -> int:
        try:
            v = int(v)
        except (TypeError, ValueError):
            v = self._min
        v = max(self._min, min(self._max, v))
        # 对齐步长
        v = self._min + round((v - self._min) / self._step) * self._step
        return max(self._min, min(self._max, v))

    def get(self) -> int:
        return self._value

    def set(self, value) -> None:
        self._value = self._clamp(value)
        self._draw()

    # ---------------------------------------------------------- 绘制

    def _frac(self) -> float:
        span = self._max - self._min
        return (self._value - self._min) / span if span else 0.0

    def _draw(self) -> None:
        self.delete("all")
        pad = 6
        x0, x1 = pad, self._cw - pad
        ty = self._track_y
        # 轨道
        self.create_line(x0, ty, x1, ty, fill=BORDER, width=4, capstyle="round")
        kx = x0 + (x1 - x0) * self._frac()
        # 已填充部分
        self.create_line(x0, ty, kx, ty, fill=ACCENT, width=4, capstyle="round")
        # 滑块
        self.create_oval(kx - 6, ty - 6, kx + 6, ty + 6, fill="#ffffff",
                         outline=ACCENT, width=2)
        # 数值
        text = self._fmt(self._value) if self._fmt else f"{self._value}{self._suffix}"
        self.create_text(pad, 7, text=text, anchor="w", fill=FG_DIM,
                         font=("Microsoft YaHei UI", 8))

    # ---------------------------------------------------------- 交互

    def _value_at(self, x: int) -> int:
        pad = 6
        x0, x1 = pad, self._cw - pad
        frac = 0.0 if x1 == x0 else (x - x0) / (x1 - x0)
        frac = max(0.0, min(1.0, frac))
        return self._clamp(self._min + frac * (self._max - self._min))

    def _apply(self, x: int) -> None:
        v = self._value_at(x)
        if v != self._value:
            self._value = v
            self._draw()
            if self._command:
                self._command(v)

    def _on_click(self, e):
        self._dragging = True
        self._apply(e.x)

    def _on_drag(self, e):
        if self._dragging:
            self._apply(e.x)

    def _on_release(self, _e):
        self._dragging = False


class Card(tk.Frame):
    """带底色的圆角卡片，内部用 bg 参数放内容。"""

    def __init__(self, master, radius: int = 8, pad: int = 12, **kwargs):
        self._bg = BG_ALT
        super().__init__(master, bg=self._bg, **kwargs)
        self.inner = tk.Frame(self, bg=self._bg)
        self.inner.pack(fill="both", expand=True, padx=pad, pady=pad)


class ScrollFrame(tk.Frame):
    """可滚动容器：用 Canvas + inner Frame，支持鼠标滚轮。"""

    def __init__(self, master, bg: str = BG, **kwargs):
        super().__init__(master, bg=bg, **kwargs)
        # width=1：Canvas 不给宽度时默认请求 378px，会把 ScrollFrame 的 reqwidth
        # 顶到 392，父容器按 req 分配空间时同排控件就被挤出窗口（窄窗口坑）。
        self._canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0, width=1)
        self._vsb = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._vsb.set)
        self._vsb.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self.inner = tk.Frame(self._canvas, bg=bg)
        self._win = self._canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._canvas.bind("<Enter>", lambda _e: self._bind_wheel(True))
        self._canvas.bind("<Leave>", lambda _e: self._bind_wheel(False))
        # 拖窗口边缘时 <Configure> 会以每像素一次的速度连环触发，
        # 每次都跑 bbox("all")（要遍历全部 item）就会卡成幻灯片。
        # 合并成 after_idle 一次、缓存上一次的 scrollregion 尺寸。
        self._scroll_job = None
        self._region = None
        self._win_w = -1
        self._win_h = -1
        self._sync_job = None
        self._sb_job = None
        self._sb_shown = True

    def _on_inner_configure(self, _e):
        # 反馈②：窗口拉伸卡顿的元凶之一就是这里同步重算 scrollregion。
        if self._scroll_job is None:
            self._scroll_job = self.after_idle(self._flush_region)

    def _flush_region(self):
        self._scroll_job = None
        try:
            box = self._canvas.bbox("all")
        except tk.TclError:
            return
        if box is None or box == self._region:
            return
        self._region = box
        try:
            self._canvas.configure(scrollregion=box)
        except tk.TclError:
            pass
        self._auto_scrollbar(box)

    def _auto_scrollbar(self, box=None):
        """内容放得下就把滚动条收起来。

        启动面板放进 ScrollFrame 后，大窗口下也常驻一条空滚动条，右侧平白
        多出一根灰条（还占 15px 宽度）。这里按内容高度和可视高度对比决定
        收不收。``_sb_shown`` 记住当前状态，状态没变就不碰（重复 pack/pack_forget
        每次都会重排整条滚动区）。
        """
        if box is None:
            box = self._region
        if not box:
            return
        try:
            need = box[3] - box[1]
            have = self._canvas.winfo_height()
        except tk.TclError:
            return
        # 留 2px 余量：滚动条出现/消失本身会改变可视宽度，避免来回抖
        want = need > have + 2
        if want == getattr(self, "_sb_shown", True):
            return
        self._sb_shown = want
        try:
            if want:
                self._vsb.pack(side="right", fill="y")
            else:
                self._vsb.pack_forget()
        except tk.TclError:
            pass

    def _on_canvas_configure(self, event):
        # 反馈②：拖窗口边框时 <Configure> 每像素触发一次，itemconfigure 改
        # create_window 的宽度会让 Canvas 里的 inner 全量重排（实测 105 个控件
        # 103 ms/次，退化版只要 26 ms）。合成到 after(80) 里做一次，拖动过程中
        # 内容暂时保持旧宽度，松手 80ms 后对齐——视觉上完全无感，手感立刻跟手。
        #
        # 高度变化也要重判滚动条，所以这段放在宽度的早退之前。
        if event.height != getattr(self, "_win_h", -1):
            self._win_h = event.height
            if getattr(self, "_sb_job", None) is None:
                self._sb_job = self.after(160, self._flush_scrollbar)
        if event.width == self._win_w:
            return
        self._win_w = event.width
        if self._sync_job is None:
            # 140 → 60 ms：外层 App 已经有 70 ms 的页面防抖（拖动全程页面不换
            # 尺寸），所以这里再等 140 ms 只是把「松手到内容对齐」又往后推了
            # 140 ms —— 实测 install 页松手总耗时里就有一帧 ~100 ms 卡在这。
            # 拖动期间 ScrollFrame 根本收不到 Configure，这个防抖只影响收尾。
            self._sync_job = self.after(60, self._flush_width)

    def _flush_scrollbar(self):
        self._sb_job = None
        self._auto_scrollbar()

    def _flush_width(self):
        self._sync_job = None
        try:
            self._canvas.itemconfigure(self._win, width=max(1, self._win_w))
        except tk.TclError:
            pass

    def _bind_wheel(self, on: bool):
        if on:
            self._canvas.bind_all("<MouseWheel>", self._on_wheel)
        else:
            self._canvas.unbind_all("<MouseWheel>")

    def _on_wheel(self, event):
        try:
            self._canvas.yview_scroll(int(-event.delta / 120), "units")
        except tk.TclError:
            pass

    def scroll_to_top(self):
        self._canvas.yview_moveto(0)


class ListRow(tk.Frame):
    """列表里的一行，支持 hover 高亮与选中态。"""

    def __init__(self, master, bg: str = BG_ALT, **kwargs):
        super().__init__(master, bg=bg, **kwargs)
        self._bg = bg
        self._selected = False
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, _e):
        if not self._selected:
            self.configure(bg=BG_HOVER)
            for child in self.winfo_children():
                try:
                    child.configure(bg=BG_HOVER)
                except tk.TclError:
                    pass

    def _on_leave(self, _e):
        if not self._selected:
            self.configure(bg=self._bg)
            for child in self.winfo_children():
                try:
                    child.configure(bg=self._bg)
                except tk.TclError:
                    pass

    def set_selected(self, value: bool):
        self._selected = value
        color = BG_ACTIVE if value else self._bg
        self.configure(bg=color)
        for child in self.winfo_children():
            try:
                child.configure(bg=color)
            except tk.TclError:
                pass


# ---------------------------------------------------------------- ttk 样式

def apply_style(root: tk.Tk) -> dict[str, tkfont.Font]:
    fonts = make_fonts()
    root.configure(bg=BG)
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure(".", background=BG, foreground=FG, font=fonts["body"],
                    fieldbackground=BG_ALT, bordercolor=BORDER,
                    lightcolor=BG_ALT, darkcolor=BG_ALT)
    style.configure("TFrame", background=BG)
    style.configure("Card.TFrame", background=BG_ALT)
    style.configure("TLabel", background=BG, foreground=FG, font=fonts["body"])
    style.configure("Dim.TLabel", background=BG, foreground=FG_DIM, font=fonts["small"])
    style.configure("H1.TLabel", background=BG, foreground=FG, font=fonts["h1"])
    style.configure("H2.TLabel", background=BG, foreground=FG, font=fonts["h2"])

    style.configure("TEntry", fieldbackground=BG_ALT, foreground=FG,
                    insertcolor=FG, bordercolor=BORDER, lightcolor=BORDER,
                    darkcolor=BORDER, padding=5)
    style.map("TEntry",
              fieldbackground=[("focus", BG_HOVER), ("disabled", BG_ALT)],
              bordercolor=[("focus", ACCENT)],
              foreground=[("disabled", FG_FAINT)])

    style.configure("TCombobox", fieldbackground=BG_ALT, background=BG_ALT,
                    foreground=FG, arrowcolor=FG_DIM, bordercolor=BORDER,
                    lightcolor=BORDER, darkcolor=BORDER, padding=4)
    style.map("TCombobox",
              fieldbackground=[("readonly", BG_ALT), ("focus", BG_HOVER)],
              foreground=[("readonly", FG)],
              selectbackground=[("readonly", BG_ALT)],
              selectforeground=[("readonly", FG)],
              bordercolor=[("focus", ACCENT)])

    style.configure("TCheckbutton", background=BG, foreground=FG,
                    indicatorbackground=BG_ALT, indicatorforeground=ACCENT,
                    focuscolor=BG)
    style.map("TCheckbutton",
              background=[("active", BG)],
              indicatorbackground=[("selected", ACCENT), ("active", BG_HOVER)],
              foreground=[("active", FG)])

    style.configure("TScrollbar", background=BG_ALT, troughcolor=BG,
                    bordercolor=BG, arrowcolor=FG_DIM, gripcount=0,
                    relief="flat")
    style.map("TScrollbar", background=[("active", BG_HOVER)])

    style.configure("TSeparator", background=BORDER)
    style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=0)
    style.configure("TNotebook.Tab", background=BG, foreground=FG_DIM,
                    padding=(16, 7), borderwidth=0, font=fonts["body"])
    style.map("TNotebook.Tab",
              background=[("selected", BG_ALT), ("active", BG_HOVER)],
              foreground=[("selected", ACCENT), ("active", FG)],
              expand=[("selected", (0, 0, 0, 0))])

    style.configure("TProgressbar", background=ACCENT, troughcolor=BG_ALT,
                    bordercolor=BG_ALT, lightcolor=ACCENT, darkcolor=ACCENT,
                    thickness=6)
    style.configure("Horizontal.TProgressbar", thickness=6)

    style.configure("Treeview", background=BG_ALT, fieldbackground=BG_ALT,
                    foreground=FG, bordercolor=BORDER, rowheight=30,
                    font=fonts["body"])
    style.configure("Treeview.Heading", background=BG, foreground=FG_DIM,
                    font=fonts["small"], relief="flat", borderwidth=0)
    style.map("Treeview",
              background=[("selected", ACCENT_DARK)],
              foreground=[("selected", "#ffffff")])
    style.map("Treeview.Heading", background=[("active", BG_HOVER)])

    style.configure("TLabelframe", background=BG, foreground=FG_DIM,
                    bordercolor=BORDER, relief="solid", borderwidth=1)
    style.configure("TLabelframe.Label", background=BG, foreground=FG_DIM,
                    font=fonts["small"])

    return fonts
