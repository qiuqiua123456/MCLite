"""通用小组件：页面基类、日志面板、进度条封装、消息条。"""

from __future__ import annotations

import threading
import tkinter as tk
from collections import deque
from tkinter import font as tkfont
from tkinter import ttk
from typing import Callable

from .theme import (
    ACCENT, BG, BG_ALT, BG_HOVER, BORDER, DANGER, FG, FG_DIM, FG_FAINT,
    SUCCESS, WARN, FlatButton, ScrollFrame,
)


class Page(tk.Frame):
    """所有页面的基类。子类实现 build()。"""

    title = "页面"
    subtitle = ""

    def __init__(self, master, app):
        super().__init__(master, bg=BG)
        self.app = app
        self.build()

    # ---------------------------------------------------------- 生命周期

    def build(self) -> None:
        raise NotImplementedError

    def on_show(self) -> None:
        """页面被切换到前台时调用。"""

    def on_hide(self) -> None:
        """页面被切走时调用。"""

    def post(self, fn) -> None:
        """线程安全地把回调排到主线程执行。"""
        try:
            self.app.post(fn)
        except Exception:                            # noqa: BLE001
            pass

    # ---------------------------------------------------------- 工具

    def header(self, parent, title: str, subtitle: str = "") -> tk.Frame:
        bar = tk.Frame(parent, bg=BG)
        tk.Label(bar, text=title, bg=BG, fg=FG,
                 font=self.app.fonts["h1"]).pack(anchor="w")
        if subtitle:
            tk.Label(bar, text=subtitle, bg=BG, fg=FG_DIM,
                     font=self.app.fonts["small"]).pack(anchor="w", pady=(2, 0))
        return bar


class LogPanel(tk.Frame):
    """只读日志面板。写入可在任意线程调用：内容先入队列，主线程定时取出。"""

    def __init__(self, master, height: int = 8, **kwargs):
        super().__init__(master, bg=BG_ALT, **kwargs)
        # width=1 是必需的：Text 不给宽度就用默认 80 字符，reqwidth 会报到 ~496px，
        # 父框的 req 被它顶大，同排的兄弟控件就被挤到窗口外面（窄窗口下的常见坑）。
        # 真正宽度由 pack(fill="both", expand=True) 决定。
        self.text = tk.Text(
            self, height=height, width=1, bg=BG_ALT, fg=FG_DIM, bd=0,
            highlightthickness=0, wrap="word", font=("Consolas", 8),
            insertbackground=FG, state="disabled", padx=8, pady=6,
        )
        self.text.pack(side="left", fill="both", expand=True)
        self._vsb = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self._vsb.pack(side="right", fill="y")
        self.text.configure(yscrollcommand=self._vsb.set)
        self.text.tag_configure("info", foreground=FG_DIM)
        self.text.tag_configure("ok", foreground=SUCCESS)
        self.text.tag_configure("warn", foreground=WARN)
        self.text.tag_configure("err", foreground=DANGER)
        self._pending: "deque[tuple[str, str]]" = deque()
        self._flush_job = self.after(60, self._flush)

    def write(self, message: str, tag: str = "info") -> None:
        self._pending.append((message, tag))

    def _flush(self) -> None:
        batch = []
        try:
            while len(batch) < 200:
                batch.append(self._pending.popleft())
        except IndexError:
            pass
        if batch:
            try:
                self.text.configure(state="normal")
                for message, tag in batch:
                    self.text.insert("end", message.rstrip() + "\n", tag)
                lines = int(self.text.index("end-1c").split(".")[0])
                if lines > 2000:
                    self.text.delete("1.0", f"{lines - 1500}.0")
                self.text.see("end")
                self.text.configure(state="disabled")
            except tk.TclError:
                pass
        try:
            self._flush_job = self.after(60, self._flush)
        except tk.TclError:
            pass

    def clear(self) -> None:
        self._pending.clear()
        try:
            self.text.configure(state="normal")
            self.text.delete("1.0", "end")
            self.text.configure(state="disabled")
        except tk.TclError:
            pass


class ProgressBar(tk.Frame):
    """自绘进度条，比 ttk 的更容易配色。"""

    def __init__(self, master, height: int = 6, **kwargs):
        super().__init__(master, bg=BG_ALT, height=height, **kwargs)
        self._h = height
        self._value = 0.0
        # width=1 同 Text：不给宽度时 Canvas 请求 378px，把整排的 req 顶大。
        self.canvas = tk.Canvas(self, bg=BG_ALT, height=height, bd=0,
                                highlightthickness=0, width=1)
        self.canvas.pack(fill="x", expand=True)
        self._bar = None
        self.canvas.bind("<Configure>", lambda _e: self._draw())

    def set(self, value: float) -> None:
        self._value = max(0.0, min(1.0, value))
        self._draw()

    def _draw(self) -> None:
        self.canvas.delete("all")
        w = self.canvas.winfo_width()
        if w <= 1:
            return
        self.canvas.create_rectangle(0, 0, w, self._h, fill=BG_HOVER, outline="")
        fw = int(w * self._value)
        if fw > 0:
            self.canvas.create_rectangle(0, 0, max(2, fw), self._h, fill=ACCENT, outline="")


class Toast(tk.Frame):
    """浮在页面底部的消息条，2.5 秒后自动消失。"""

    def __init__(self, master):
        super().__init__(master, bg=BORDER, padx=1, pady=1)
        self._inner = tk.Frame(self, bg=BG_ALT, padx=14, pady=8)
        self._inner.pack(fill="both", expand=True)
        self._label = tk.Label(self._inner, text="", bg=BG_ALT, fg=FG,
                               font=("Microsoft YaHei UI", 9))
        self._label.pack()
        self._job = None
        self.place_forget()

    def show(self, text: str, kind: str = "info") -> None:
        color = {"ok": SUCCESS, "warn": WARN, "err": DANGER}.get(kind, FG)
        self._label.configure(text=text, fg=color)
        self.place(relx=0.5, rely=0.96, anchor="s")
        self.lift()
        if self._job:
            try:
                self.after_cancel(self._job)
            except tk.TclError:
                pass
        self._job = self.after(2600, self._hide)

    def _hide(self) -> None:
        self._job = None
        try:
            self.place_forget()
        except tk.TclError:
            pass


class SelectableRow(tk.Frame):
    """一行可点选的条目容器，带 hover / 选中底色。"""

    def __init__(self, master, on_click: Callable[[], None] | None = None,
                 bg: str = BG_ALT, pad: int = 10):
        super().__init__(master, bg=bg)
        self._base_bg = bg
        self._selected = False
        self._on_click = on_click
        self.inner = tk.Frame(self, bg=bg, padx=pad, pady=pad)
        self.inner.pack(fill="both", expand=True)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        if on_click:
            self.bind("<Button-1>", self._click)
            self.inner.bind("<Button-1>", self._click)

    def _paint(self, color: str) -> None:
        def walk(w):
            for child in w.winfo_children():
                try:
                    child.configure(bg=color)
                except tk.TclError:
                    pass
                walk(child)
        try:
            self.configure(bg=color)
        except tk.TclError:
            pass
        walk(self)

    def _inside(self) -> bool:
        """指针现在是否还停在整行（含所有子控件）范围内。"""
        try:
            node = self.winfo_containing(*self.winfo_pointerxy())
        except tk.TclError:
            return False
        while node is not None:
            if node is self:
                return True
            try:
                node = node.master
            except Exception:
                return False
        return False

    def _settle(self) -> None:
        """等本轮事件跑完再决定颜色，避免父/子 Enter·Leave 互相打架。"""
        if self._selected:
            self._paint(BG_HOVER)
        else:
            self._paint(BG_HOVER if self._inside() else self._base_bg)

    def _enter(self, _e=None):
        if not self._selected:
            self.after_idle(self._settle)

    def _leave(self, _e=None):
        if not self._selected:
            self.after_idle(self._settle)

    def attach(self):
        """把点击/悬停绑到全部子控件上。

        Tk 的鼠标事件**不会**向父控件冒泡，所以只绑 self 的话，
        点在文字标签上就毫无反应。子控件通常是在 SelectableRow 建好之后
        才 pack 进去的，因此调用方需要在这里显式调一次 attach()。
        """
        def walk(w):
            for child in w.winfo_children():
                try:
                    child.bind("<Button-1>", self._click, add="+")
                    child.bind("<Enter>", self._enter, add="+")
                    child.bind("<Leave>", self._leave, add="+")
                    if self._on_click:
                        child.configure(cursor="hand2")
                except tk.TclError:
                    pass
                walk(child)

        walk(self)
        return self

    def _click(self, _e=None):
        if self._on_click:
            self._on_click()

    def set_selected(self, value: bool):
        self._selected = value
        self._paint(BG_HOVER if value else self._base_bg)


class TabBar(tk.Frame):
    """页签栏：文字 + 下划线，用来把「启动 / 模组 / 资源 / 账户」放进同一页。

    之前这些分别是独立导航页或弹窗，用户反馈「单开一页/单开一个弹窗不方便」，
    改成页签后切起来是一瞬间的事，也不会再弹窗。
    """

    def __init__(self, master, items, on_change=None, bg: str = BG,
                 height: int = 42, font=None, font_active=None, gap: int = 26):
        self._items = list(items)
        self._font = font or ("Microsoft YaHei UI", 10)
        self._font_active = font_active or ("Microsoft YaHei UI", 10, "bold")

        # 不要 pack_propagate(False)：那样 Frame 不会从子控件取宽度，必须自己
        # 算像素宽，字号/DPI 一变就把后面的页签挤掉（之前"账户"页签整条看不见）。
        # 让 Frame 自动收缩到子控件大小，页签数量与文字长度都无所谓。
        super().__init__(master, bg=bg)
        self._on_change = on_change
        self._bg = bg
        self._current = ""
        self._tabs: dict[str, tuple[tk.Label, tk.Frame]] = {}

        for key, text in self._items:
            holder = tk.Frame(self, bg=bg)
            holder.pack(side="left", padx=(0, gap))
            lbl = tk.Label(holder, text=text, bg=bg, fg=FG_DIM,
                           font=self._font, cursor="hand2")
            lbl.pack()
            bar = tk.Frame(holder, bg=bg, height=2)
            bar.pack(fill="x", pady=(6, 0))
            for w in (holder, lbl, bar):
                w.bind("<Button-1>", lambda _e, k=key: self.set(k, fire=True))
            self._tabs[key] = (lbl, bar)

        if self._items:
            self.set(self._items[0][0])

    # ---------------------------------------------------------- 取值

    def get(self) -> str:
        return self._current

    def set(self, key: str, fire: bool = False) -> None:
        if key not in self._tabs:
            return
        changed = key != self._current
        self._current = key
        for k, (lbl, bar) in self._tabs.items():
            on = k == key
            try:
                lbl.configure(fg=ACCENT if on else FG_DIM,
                              font=self._font_active if on else self._font)
                bar.configure(bg=ACCENT if on else self._bg)
            except tk.TclError:
                pass
        if fire and changed and self._on_change is not None:
            try:
                self._on_change(key)
            except Exception:                        # noqa: BLE001
                pass


class Select(tk.Frame):
    """自绘下拉选择器。

    为什么不用 ttk.Combobox：它的弹出列表是原生 Tk 控件，暗色主题下配色
    无法跟随，和整体风格割裂（项目里出现过一次"框内文字被截断"的问题）。
    """

    def __init__(self, master, values: list[str] | tuple[str, ...] = (),
                 value: str = "", on_change: Callable[[str], None] | None = None,
                 width: int = 30, height: int = 32, bg: str = BG_ALT,
                 pad: int = 10, max_rows: int = 12, font=None):
        super().__init__(master, bg=bg, height=height, width=width * 7)
        self._values = list(values)
        self._value = value or (self._values[0] if self._values else "")
        self._on_change = on_change
        self._bg = bg
        self._height = height
        self._max_rows = max_rows
        self._font = font or ("Microsoft YaHei UI", 9)
        self._popup: tk.Toplevel | None = None
        self.pack_propagate(False)

        self._label = tk.Label(self, text=self._value, bg=bg, fg=FG, anchor="w",
                               font=self._font, padx=pad)
        self._label.pack(side="left", fill="both", expand=True)
        self._arrow = tk.Label(self, text="▾", bg=bg, fg=FG_DIM,
                               font=self._font, padx=8)
        self._arrow.pack(side="right", fill="y")
        for w in (self, self._label, self._arrow):
            w.bind("<Button-1>", self._toggle)
            w.configure(cursor="hand2")

    # ---------------------------------------------------------- 取值
    def get(self) -> str:
        return self._value

    def set(self, value: str) -> None:
        self._value = value
        try:
            self._label.configure(text=value)
        except tk.TclError:
            pass

    def set_values(self, values) -> None:
        self._values = list(values)
        if self._value not in self._values:
            self._value = self._values[0] if self._values else ""
        self.set(self._value)

    # ---------------------------------------------------------- 弹层
    def _toggle(self, _e=None) -> None:
        if self._popup is not None:
            self._close()
        else:
            self._open()

    def _open(self) -> None:
        if not self._values:
            return
        top = tk.Toplevel(self)
        top.overrideredirect(True)
        top.configure(bg=BORDER)
        self._popup = top
        try:
            x = self.winfo_rootx()
            y = self.winfo_rooty() + self.winfo_height() + 2
            rows = min(len(self._values), self._max_rows)
            h = rows * 30 + 2
            top.geometry(f"{max(self.winfo_width(), 180)}x{h}+{x}+{y}")
        except tk.TclError:
            pass
        body = tk.Frame(top, bg=BG_ALT)
        body.pack(fill="both", expand=True, padx=1, pady=1)
        canvas = tk.Canvas(body, bg=BG_ALT, bd=0, highlightthickness=0)
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas, bg=BG_ALT)
        canvas.create_window((0, 0), window=inner, anchor="nw", tags="win")
        inner.bind("<Configure>",
                   lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure("win", width=e.width))
        for value in self._values:
            row = tk.Frame(inner, bg=BG_ALT, height=30)
            row.pack(fill="x")
            row.pack_propagate(False)
            lbl = tk.Label(row, text=value, bg=BG_ALT,
                           fg=(ACCENT if value == self._value else FG),
                           anchor="w", font=self._font, padx=10)
            lbl.pack(fill="both", expand=True)
            for w in (row, lbl):
                w.bind("<Button-1>", lambda _e, v=value: self._choose(v))
                w.bind("<Enter>", lambda _e, r=row, l=lbl: (
                    r.configure(bg=BG_HOVER), l.configure(bg=BG_HOVER)))
                w.bind("<Leave>", lambda _e, r=row, l=lbl: (
                    r.configure(bg=BG_ALT), l.configure(bg=BG_ALT)))
        if len(self._values) > self._max_rows:
            sb = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
            sb.pack(side="right", fill="y")
            canvas.configure(yscrollcommand=sb.set)
        canvas.bind("<MouseWheel>",
                    lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))
        top.bind("<Escape>", lambda _e: self._close())
        top.bind("<FocusOut>", lambda _e: self._close())
        try:
            top.grab_set()
            top.focus_force()
        except tk.TclError:
            pass

    def _choose(self, value: str) -> None:
        self._close()
        if value == self._value:
            return
        self.set(value)
        if self._on_change:
            try:
                self._on_change(value)
            except Exception:                         # noqa: BLE001
                pass

    def _close(self) -> None:
        top, self._popup = self._popup, None
        if top is None:
            return
        try:
            top.grab_release()
        except tk.TclError:
            pass
        try:
            top.destroy()
        except tk.TclError:
            pass


class TaskDialog(tk.Toplevel):
    """跑一个后台任务的小窗口：进度条 + 日志 + 取消。

    worker 的签名是 `worker(log, progress, cancelled)`，返回 `(ok, message)`；
    它跑在守护线程里，所以内部只能用 `log()`/`progress()` 回传，别碰控件。
    """

    def __init__(self, master, title: str, width: int = 640, height: int = 430,
                 ok_text: str = "完成"):
        super().__init__(master)
        self.title(title)
        self.configure(bg=BG)
        self.geometry(f"{width}x{height}")
        self.resizable(False, False)
        self._result = None
        self._done = False
        self._cancelled = threading.Event()
        self._on_done = None

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=(16, 12))
        tk.Label(body, text=title, bg=BG, fg=FG,
                 font=("Microsoft YaHei UI", 13, "bold")).pack(anchor="w")
        self._hint = tk.Label(body, text="正在准备…", bg=BG, fg=FG_DIM,
                              font=("Microsoft YaHei UI", 9))
        self._hint.pack(anchor="w", pady=(4, 10))
        self.progress = ProgressBar(body, height=8)
        self.progress.pack(fill="x")
        self.log = LogPanel(body, height=13)
        self.log.pack(fill="both", expand=True, pady=(10, 0))

        bottom = tk.Frame(body, bg=BG)
        bottom.pack(fill="x", pady=(10, 0))
        self._cancel_btn = FlatButton(bottom, "取消", command=self._cancel,
                                      kind="danger", height=32, width=88, bg=BG)
        self._cancel_btn.pack(side="right")
        self._ok_btn = FlatButton(bottom, ok_text, command=self._close,
                                  kind="primary", height=32, width=88, bg=BG)
        self._ok_btn.pack(side="right", padx=8)
        self._ok_btn.set_enabled(False)
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self._center(master, width, height)

    def _center(self, master, w: int, h: int) -> None:
        try:
            self.update_idletasks()
            x = master.winfo_rootx() + (master.winfo_width() - w) // 2
            y = master.winfo_rooty() + (master.winfo_height() - h) // 2
            self.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")
        except tk.TclError:
            pass

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def set_hint(self, text: str, color: str = "") -> None:
        self._hint.configure(text=text, fg=color or FG_DIM)

    def run(self, worker, on_done=None) -> None:
        self._on_done = on_done

        def log(msg: str, tag: str = "info") -> None:
            self.log.write(str(msg), tag)

        def progress(value: float, text: str = "") -> None:
            def apply() -> None:
                try:
                    self.progress.set(value)
                    if text:
                        self._hint.configure(text=text)
                except tk.TclError:
                    pass

            self.after(0, apply)

        def target() -> None:
            try:
                ok, msg = worker(log, progress, self._cancelled)
            except Exception as exc:                  # noqa: BLE001
                ok, msg = False, f"{type(exc).__name__}: {exc}"
                log(msg, "err")
            self.after(0, lambda: self._finish(bool(ok), str(msg)))

        threading.Thread(target=target, daemon=True).start()

    def _finish(self, ok: bool, msg: str) -> None:
        self._done = True
        self._result = (ok, msg)
        try:
            self.progress.set(1.0 if ok else 0.0)
            self.set_hint(msg, SUCCESS if ok else DANGER)
            self._ok_btn.set_enabled(True)
            self._cancel_btn.set_text("关闭")
        except tk.TclError:
            pass
        if self._on_done is not None:
            try:
                self._on_done(ok, msg)
            except Exception:                        # noqa: BLE001
                pass

    def _cancel(self) -> None:
        if self._done:
            self._close()
            return
        self._cancelled.set()
        try:
            self.set_hint("正在取消…", WARN)
            self._cancel_btn.set_enabled(False)
        except tk.TclError:
            pass

    def _close(self) -> None:
        try:
            self.grab_release()
        except tk.TclError:
            pass
        try:
            self.destroy()
        except tk.TclError:
            pass


class Avatar(tk.Canvas):
    """圆形头像：有图片就画图片，没有就画首字母。"""

    def __init__(self, master, size: int = 36, bg: str = BG, border: str = ""):
        super().__init__(master, width=size, height=size, bg=bg,
                         bd=0, highlightthickness=0)
        self._size = size
        self._bg = bg
        self._border = border or BG_HOVER
        self._photo = None
        self._name = ""
        self.draw_letter("?")

    def draw_letter(self, name: str) -> None:
        self._name = name or "?"
        self._photo = None
        self._redraw()

    def draw_image(self, png_bytes: bytes) -> bool:
        """用 PNG 字节设置头像（Tk 8.6 原生支持，不需要 Pillow）。"""
        import base64

        try:
            self._photo = tk.PhotoImage(data=base64.b64encode(png_bytes).decode("ascii"))
        except tk.TclError:
            self._photo = None
            return False
        self._redraw()
        return True

    def draw_skin(self, skin_png: bytes) -> bool:
        """从整张皮肤图里抠出 8x8 的脸，缩放到当前尺寸。

        用 Tk 自带的 `photo copy -from/-zoom`，避免为此引入 Pillow。
        """
        import base64

        try:
            src = tk.PhotoImage(data=base64.b64encode(skin_png).decode("ascii"))
        except tk.TclError:
            return False
        n = self._size - 2
        sw, sh = src.width(), src.height()
        if sw < 16 or sh < 16:
            return False
        try:
            face = tk.PhotoImage(width=8, height=8)
            face.tk.call(face, "copy", src, "-from", 8, 8, 16, 16, "-to", 0, 0)
            zoom = max(1, n // 8)
            big = tk.PhotoImage(width=8 * zoom, height=8 * zoom)
            big.tk.call(big, "copy", face, "-zoom", zoom, zoom)
            self._photo = big
        except tk.TclError:
            return False
        self._redraw()
        return True

    def _redraw(self) -> None:
        self.delete("all")
        n = self._size
        self.create_oval(1, 1, n - 1, n - 1, fill=BORDER, outline="")
        if self._photo is not None:
            self.create_image(n // 2, n // 2, image=self._photo)
        else:
            letter = (self._name.strip() or "?")[0].upper()
            self.create_text(n // 2, n // 2 + 1, text=letter,
                             fill=FG, font=("Microsoft YaHei UI", max(10, n // 3), "bold"))

    def set_size(self, size: int) -> None:
        self._size = size
        self.configure(width=size, height=size)
        self._redraw()
