"""崩溃诊断弹窗：把 crash.analyze 的结论摆在用户面前，并给出下一步动作。"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path

from .theme import (
    ACCENT, BG, BG_ALT, BG_HOVER, BORDER, DANGER, FG, FG_DIM, FG_FAINT, SUCCESS,
    FlatButton,
)
from .widgets import ScrollFrame


class CrashDialog(tk.Toplevel):
    def __init__(self, app, version_id: str, diags, source: Path | None = None) -> None:
        super().__init__(app)
        self.app = app
        self.version_id = version_id
        self.diags = diags
        self.source = source
        self.title("游戏异常退出")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(app)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Escape>", lambda _e: self._close())
        self._build()
        self._center()

    # ------------------------------------------------------------ 布局

    def _build(self) -> None:
        pad = tk.Frame(self, bg=BG, padx=22, pady=18)
        pad.pack(fill="both", expand=True)

        head = tk.Frame(pad, bg=BG)
        head.pack(fill="x")
        tk.Label(head, text="游戏异常退出", bg=BG, fg=FG,
                 font=("Segoe UI", 15, "bold")).pack(anchor="w")
        tk.Label(head, text=self.version_id, bg=BG, fg=FG_FAINT,
                 font=self.app.fonts["small"]).pack(anchor="w", pady=(2, 0))

        tk.Label(pad,
                 text="下面是根据日志推断出的原因，按可能性从高到低排列：",
                 bg=BG, fg=FG_DIM, font=self.app.fonts["small"]).pack(anchor="w", pady=(12, 8))

        holder = tk.Frame(pad, bg=BG_ALT, highlightthickness=1, highlightbackground=BORDER)
        holder.pack(fill="both", expand=True)
        self._scroll = ScrollFrame(holder, bg=BG_ALT, height=210)
        self._scroll.pack(fill="both", expand=True, padx=1, pady=1)
        for i, diag in enumerate(self.diags):
            self._card(i, diag)
        self._scroll.inner.update_idletasks()
        self._scroll.scroll_to_top()

        bottom = tk.Frame(pad, bg=BG)
        bottom.pack(fill="x", pady=(14, 0))
        FlatButton(bottom, "一键反馈", command=self._feedback, kind="primary",
                   height=32, width=96, bg=BG).pack(side="left")
        FlatButton(bottom, "复制诊断", command=self._copy, kind="normal",
                   height=32, width=92, bg=BG).pack(side="left", padx=8)
        FlatButton(bottom, "打开日志", command=self._open_log, kind="ghost",
                   height=32, width=88, bg=BG).pack(side="left")
        FlatButton(bottom, "关闭", command=self._close, kind="normal",
                   height=32, width=76, bg=BG).pack(side="right")

    def _card(self, index: int, diag) -> None:
        card = tk.Frame(self._scroll.inner, bg=BG_ALT, padx=12, pady=10)
        card.pack(fill="x")
        if index:
            tk.Frame(card, bg=BORDER, height=1).pack(fill="x", pady=(0, 8))

        top = tk.Frame(card, bg=BG_ALT)
        top.pack(fill="x")
        dot = tk.Canvas(top, width=8, height=8, bg=BG_ALT, highlightthickness=0, bd=0)
        dot.pack(side="left", pady=(6, 0))
        dot.create_oval(0, 0, 8, 8, fill=DANGER if index == 0 else FG_FAINT, outline="")
        tk.Label(top, text=diag.title, bg=BG_ALT, fg=FG,
                 font=self.app.fonts["body"], wraplength=470,
                 justify="left").pack(side="left", padx=(8, 0))

        if diag.detail:
            tk.Label(card, text=diag.detail[:180], bg=BG_ALT, fg=FG_DIM,
                     font=("Consolas", 9), wraplength=490,
                     justify="left").pack(anchor="w", padx=(16, 0), pady=(3, 0))
        for hint in diag.hints:
            tk.Label(card, text=f"· {hint}", bg=BG_ALT, fg=FG_DIM,
                     font=self.app.fonts["small"], wraplength=490,
                     justify="left").pack(anchor="w", padx=(16, 0), pady=(2, 0))

    def _center(self) -> None:
        self.update_idletasks()
        w, h = 580, 470
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2 - 40}")

    # ------------------------------------------------------------ 动作

    def _all_text(self) -> str:
        lines = [f"MCLite 崩溃诊断 — {self.version_id}", ""]
        for d in self.diags:
            lines.append(d.text)
            lines.append("")
        return "\n".join(lines)

    def _copy(self) -> None:
        try:
            self.clipboard_clear()
            self.clipboard_append(self._all_text())
            self.update_idletasks()
        except tk.TclError:
            return
        self.app.notify("诊断结果已复制到剪贴板", "ok")

    def _open_log(self) -> None:
        from ..mods import open_folder
        if self.source is not None and Path(self.source).is_file():
            open_folder(Path(self.source).parent)
        else:
            open_folder(Path(self.app.cfg.game_dir) / "logs")

    def _feedback(self) -> None:
        from .. import feedback

        def work():
            try:
                path = feedback.collect(self.app.cfg, getattr(self.app, "_javas", None))
            except Exception as exc:                 # noqa: BLE001
                self.app.post(lambda: self.app.notify(f"打包失败：{exc}", "err"))
                return
            self.app.post(lambda: self.app.notify(f"反馈包已保存到桌面：{path.name}", "ok"))
        import threading
        threading.Thread(target=work, daemon=True).start()
        self.app.notify("正在打包日志…", "info")

    def _close(self) -> None:
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
