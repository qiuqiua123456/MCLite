"""完整性检查弹窗：校验版本、库、资源，并一键补齐缺失文件。"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path

from .theme import (
    BG, BG_ALT, BORDER, DANGER, FG, FG_DIM, FG_FAINT, SUCCESS, WARN,
    FlatButton,
)
from .widgets import LogPanel, ProgressBar, ScrollFrame, SelectableRow

_KIND_LABEL = {"jar": "客户端", "library": "库文件", "asset": "资源文件",
               "log4j": "日志配置", "natives": "本机库"}


class VerifyDialog(tk.Toplevel):
    def __init__(self, app, version_id: str) -> None:
        super().__init__(app)
        self.app = app
        self.version_id = version_id
        self.report = None
        self._busy = False
        self._cancel = threading.Event()
        self.title(f"完整性检查 — {version_id}")
        self.configure(bg=BG)
        self.transient(app)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Escape>", lambda _e: self._close())
        self._build()
        self._center()
        self.after(120, self.start)

    # ------------------------------------------------------------ 布局

    def _build(self) -> None:
        pad = tk.Frame(self, bg=BG, padx=18, pady=16)
        pad.pack(fill="both", expand=True)

        head = tk.Frame(pad, bg=BG)
        head.pack(fill="x")
        tk.Label(head, text="完整性检查", bg=BG, fg=FG,
                 font=self.app.fonts["h2"]).pack(side="left")
        tk.Label(head, text=self.version_id, bg=BG, fg=FG_FAINT,
                 font=self.app.fonts["small"]).pack(side="right")

        self._summary = tk.Label(pad, text="正在检查…", bg=BG, fg=FG_DIM,
                                 font=self.app.fonts["small"])
        self._summary.pack(anchor="w", pady=(8, 10))

        holder = tk.Frame(pad, bg=BG_ALT, highlightthickness=1,
                          highlightbackground=BORDER)
        holder.pack(fill="both", expand=True)
        self._scroll = ScrollFrame(holder, bg=BG_ALT)
        self._scroll.pack(fill="both", expand=True, padx=1, pady=1)

        self._bar = ProgressBar(pad, height=6)
        self._bar.pack(fill="x", pady=(10, 0))
        self._log = LogPanel(pad, height=7)
        self._log.pack(fill="x", pady=(8, 0))

        bottom = tk.Frame(pad, bg=BG)
        bottom.pack(fill="x", pady=(12, 0))
        self._fix_btn = FlatButton(bottom, "一键修复", command=self.start_repair,
                                   kind="primary", height=32, width=96, bg=BG)
        self._fix_btn.pack(side="left")
        self._fix_btn.set_enabled(False)
        self._again_btn = FlatButton(bottom, "重新检查", command=self.start,
                                     kind="normal", height=32, width=88, bg=BG)
        self._again_btn.pack(side="left", padx=8)
        FlatButton(bottom, "打开版本目录", command=self._open_dir, kind="ghost",
                   height=32, width=108, bg=BG).pack(side="left")
        FlatButton(bottom, "关闭", command=self._close, kind="normal",
                   height=32, width=72, bg=BG).pack(side="right")

    def _center(self) -> None:
        self.update_idletasks()
        w, h = 700, 540
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2 - 30}")

    # ------------------------------------------------------------ 检查

    def start(self) -> None:
        if self._busy:
            return
        from .. import verify

        self._busy = True
        self._cancel.clear()
        self._fix_btn.set_enabled(False)
        self._again_btn.set_enabled(False)
        self._summary.configure(text="正在检查版本文件…", fg=FG_DIM)
        for child in self._scroll.inner.winfo_children():
            child.destroy()
        self._log.write("开始检查…")
        game_dir = Path(self.app.cfg.game_dir)

        def work() -> None:
            try:
                report = verify.check(game_dir, self.version_id)
            except Exception as exc:                   # noqa: BLE001
                self.app.post(lambda: self._failed(str(exc)))
                return
            self.app.post(lambda: self._show(report))

        threading.Thread(target=work, daemon=True).start()

    def _show(self, report) -> None:
        self._busy = False
        self.report = report
        missing = list(report.missing or [])
        total = report.checked
        if not missing and report.jar_ok:
            self._summary.configure(
                text=f"检查完毕：{total} 个文件全部正常 ✓", fg=SUCCESS)
            tk.Label(self._scroll.inner, text="一切正常，可以直接启动游戏。", bg=BG_ALT,
                     fg=FG_DIM, font=self.app.fonts["body"]).pack(pady=40)
        else:
            head = f"检查完毕：校验 {total} 个文件，缺失 {len(missing)} 个"
            if not report.jar_ok:
                head += "（客户端 jar 缺失）"
            self._summary.configure(text=head, fg=WARN if missing else DANGER)
            groups: dict[str, list] = {}
            for item in missing:
                groups.setdefault(item.kind, []).append(item)
            for kind, items in groups.items():
                tk.Label(self._scroll.inner,
                         text=f"{_KIND_LABEL.get(kind, kind)}（{len(items)}）",
                         bg=BG_ALT, fg=FG_DIM,
                         font=self.app.fonts["small"]).pack(anchor="w", padx=10, pady=(8, 2))
                for item in items[:40]:
                    row = SelectableRow(self._scroll.inner, None, bg=BG_ALT, pad=7)
                    row.pack(fill="x")
                    tk.Label(row.inner, text=item.name, bg=BG_ALT, fg=FG,
                             font=("Consolas", 9), anchor="w").pack(fill="x")
                    size = f"{item.size / 1048576:.1f} MB" if item.size else ""
                    tk.Label(row.inner, text=size, bg=BG_ALT, fg=FG_FAINT,
                             font=self.app.fonts["small"]).pack(anchor="w")
                    row.attach()
                if len(items) > 40:
                    tk.Label(self._scroll.inner, text=f"…… 还有 {len(items) - 40} 个",
                             bg=BG_ALT, fg=FG_FAINT,
                             font=self.app.fonts["small"]).pack(anchor="w", padx=10, pady=2)
        self._scroll.inner.update_idletasks()
        self._scroll.scroll_to_top()
        self._fix_btn.set_enabled(bool(missing) or not report.jar_ok)
        self._again_btn.set_enabled(True)
        self._log.write(self._summary.cget("text"))

    def _failed(self, msg: str) -> None:
        self._busy = False
        self._summary.configure(text=f"检查失败：{msg}", fg=DANGER)
        self._again_btn.set_enabled(True)

    # ------------------------------------------------------------ 修复

    def start_repair(self) -> None:
        if self._busy:
            return
        from .. import verify

        self._busy = True
        self._cancel.clear()
        self._fix_btn.set_enabled(False)
        self._again_btn.set_enabled(False)
        self._bar.set(0)
        self._log.write("开始补齐缺失文件…")
        game_dir = Path(self.app.cfg.game_dir)

        def work() -> None:
            try:
                ok, msg = verify.repair(game_dir, self.version_id,
                                        on_log=lambda m: self.app.post(
                                            lambda mm=m: self._log.write(mm)),
                                        progress_cb=lambda p: self.app.post(
                                            lambda pp=p: self._bar.set(
                                                pp.done / pp.total if pp.total else 0)),
                                        cancel=self._cancel)
            except Exception as exc:                   # noqa: BLE001
                self.app.post(lambda: self._repair_done(False, str(exc)))
                return
            self.app.post(lambda: self._repair_done(ok, msg))

        threading.Thread(target=work, daemon=True).start()

    def _repair_done(self, ok: bool, msg: str) -> None:
        self._busy = False
        self._bar.set(1 if ok else 0)
        self._log.write(msg)
        self.app.notify(msg, "ok" if ok else "err")
        self.start()

    def _open_dir(self) -> None:
        from ..mods import open_folder

        open_folder(Path(self.app.cfg.game_dir) / "versions" / self.version_id)

    def _close(self) -> None:
        self._cancel.set()
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
