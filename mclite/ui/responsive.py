"""窄窗口下的自适应布局助手。

用户反馈（m11028）「在往小调整窗口的时候自动调整分辨率使按键能够完整显示」：
页面里有好几排按钮是用 ``pack(side="left")`` 横着摆的，宽度固定。窗口一窄，
pack 只能把**最后打包的那几个**压扁，压不动就直接推到窗口外面——用户看到的
就是「按钮只剩半个」。

Tk 的 pack/grid 不会自动换行，所以这里给一个 ``FlowRow``：它用 ``place``
把子控件排成流式多行，放不下就换行，自身高度随之变化。按钮因此永远不会被
挤出可视区。

实测（``tools/probe_hclip.py``，判据 ``winfo_reqwidth() > winfo_width()+2``
即「控件被压得比它要求的小」）：
    880x560 窗口（页面 651x512）home 被压 21 个控件（最狠的 Frame 想要
    820 只有 603）、install 18 个、settings 7 个 —— 全部集中在这些横排上。
"""

from __future__ import annotations

import tkinter as tk

from .theme import BG


def left_width(total: int, right_min: int = 400, gap: int = 18,
               lo: int = 232, hi: int = 380) -> int:
    """算左栏该多宽。

    右栏（启动面板 / 版本详情）里有几排固定宽度的按钮，实测最少要 400px 才
    不会把「导出」「获取版本清单」这类按钮挤出边界，所以左栏只能让步：
    先按 ``total - gap - right_min`` 收缩，收到底线 ``lo`` 为止。
    """
    want = int(total) - int(gap) - int(right_min)
    if want < lo:
        return lo
    if want > hi:
        return hi
    return want


class FlowRow(tk.Frame):
    """横向按钮行，宽度不够时自动换行。

    - 加控件用 ``add(widget)``。宽度取 ``winfo_reqwidth()``（按钮的画布宽度），
      高度取 ``winfo_reqheight()``；布局用 ``place``，所以这些控件不能再被
      ``pack``/``grid``（``add`` 里会先 ``pack_forget`` 一次）。
    - ``reflow(width)`` 重新排一次；宽度传页面宽度，或者留空取自己的真实宽度。
    - 行高会跟着行数变，所以外面 pack 它时用 ``fill="x"`` 即可（不要给固定高度）。
    """

    def __init__(self, master, gap: int = 6, row_gap: int = 6,
                 bg: str = BG, **kwargs):
        super().__init__(master, bg=bg, **kwargs)
        self._gap = gap
        self._row_gap = row_gap
        self._items: list[tk.Widget] = []
        self._rows = 0

    # ------------------------------------------------------------ 组装
    def add(self, widget: tk.Widget) -> tk.Widget:
        try:
            widget.pack_forget()
        except tk.TclError:
            pass
        self._items.append(widget)
        return widget

    def add_all(self, *widgets: tk.Widget) -> None:
        for w in widgets:
            self.add(w)

    @property
    def items(self) -> list[tk.Widget]:
        return list(self._items)

    # ------------------------------------------------------------ 排布
    def reflow(self, width: int | None = None) -> int:
        """重排，返回占用的总高度。"""
        if not self._items:
            return 0
        try:
            avail = int(width) if width else self.winfo_width()
        except tk.TclError:
            return 0
        if avail <= 1:
            avail = max(1, self.winfo_reqwidth())

        x = 0
        y = 0
        row_h = 0
        rows = 1
        for w in self._items:
            try:
                if not w.winfo_exists():
                    continue
                iw = max(1, w.winfo_reqwidth())
                ih = max(1, w.winfo_reqheight())
            except tk.TclError:
                continue
            if x and x + iw > avail:
                x = 0
                y += row_h + self._row_gap
                row_h = 0
                rows += 1
            try:
                w.place(x=x, y=y, width=iw, height=ih)
            except tk.TclError:
                continue
            x += iw + self._gap
            row_h = max(row_h, ih)

        total = y + row_h
        self._rows = rows
        try:
            # 父级用 fill="x" 时宽度由 pack 决定，这里只钉高度；
            # 关掉 propagate 才能让 pack 的宽度分配生效。
            self.pack_propagate(False)
            self.configure(height=total)
        except tk.TclError:
            pass
        return total

    @property
    def rows(self) -> int:
        return self._rows


def _wraplen(node) -> int:
    """读 Label 的 wraplength。

    ⚠ 必须过一遍 str()：tkinter 有时把 cget 结果包成 ``Tcl_Obj``，直接
    ``int(...)`` 会抛 TypeError——而它的调用方（页面 on_resize）外面有 try，
    异常被静默吞掉，症状就是「自适应完全没生效」。
    """
    try:
        return int(str(node.cget("wraplength")) or 0)
    except (tk.TclError, TypeError, ValueError):
        return 0


def wrap_labels(root, width: int, min_width: int = 60) -> int:
    """把 root 子树里过宽的文字标签改成自动换行，返回改动个数。

    Tk 的 Label 默认不换行，一行长提示（「从 Mojang 官方源下载到 runtime
    目录」这类）在窄窗口下会把整行撑到 req 638px，父框只有 589 → 直接被裁。
    这里只动纯文字标签，带图片的不碰（图片不能靠 wraplength 缩）。
    """
    avail = max(min_width, int(width))
    changed = 0
    stack = [root]
    while stack:
        node = stack.pop()
        try:
            kids = node.winfo_children()
        except tk.TclError:
            continue
        stack.extend(kids)
        if node.winfo_class() != "Label":
            continue
        try:
            if bool(node.cget("image")):
                continue
            if not str(node.cget("text") or "").strip():
                continue
            if _wraplen(node) == avail:
                continue
            if node.winfo_reqwidth() <= avail + 2:
                continue
            node.configure(wraplength=avail)
            changed += 1
        except (tk.TclError, ValueError):
            continue
    return changed


def fix_clipped(root, min_width: int = 56) -> int:
    """把「已经被压得比需要窄」的文字标签改成按当前宽度换行，返回改动个数。

    `wrap_labels` 是按容器宽度算的，管不到「同一行里兄弟控件把它挤窄」的情况
    （设置页「自动下载」那行，提示语 req 199 只有 150，末几个字直接被裁）。
    这里按**实测宽度**兜底：既然它只有 150px，就让它在 150px 处换行、长成两行。
    要在布局稳定之后再调（页面 on_resize 里排一个 after(120)）。
    """
    changed = 0
    stack = [root]
    while stack:
        node = stack.pop()
        try:
            kids = node.winfo_children()
        except tk.TclError:
            continue
        stack.extend(kids)
        if node.winfo_class() != "Label":
            continue
        try:
            if bool(node.cget("image")):
                continue
            if not str(node.cget("text") or "").strip():
                continue
            got = node.winfo_width()
            req = node.winfo_reqwidth()
            if got <= 1 or req <= got + 2:
                continue
            target = max(min_width, got - 4)
            if _wraplen(node) == target:
                continue
            node.configure(wraplength=target)
            changed += 1
        except (tk.TclError, ValueError):
            continue
    return changed
