"""存档管理弹窗：列出世界、备份成 zip、从备份恢复、删除。"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from .theme import (
    ACCENT, BG, BG_ALT, BORDER, DANGER, FG, FG_DIM, FG_FAINT, SUCCESS,
    FlatButton,
)
from .widgets import LogPanel, ProgressBar, ScrollFrame, SelectableRow


class WorldDialog(tk.Toplevel):
    def __init__(self, app, base_dir: Path, title: str = "") -> None:
        super().__init__(app)
        self.app = app
        self.base = Path(base_dir)
        self.rows: dict[str, SelectableRow] = {}
        self.selected = None
        self._busy = False
        self.title("存档管理" + (f" — {title}" if title else ""))
        self.configure(bg=BG)
        self.transient(app)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Escape>", lambda _e: self._close())
        self._build()
        self._center()
        self.reload()

    # ------------------------------------------------------------ 布局

    def _build(self) -> None:
        pad = tk.Frame(self, bg=BG, padx=18, pady=16)
        pad.pack(fill="both", expand=True)

        head = tk.Frame(pad, bg=BG)
        head.pack(fill="x")
        tk.Label(head, text="存档管理", bg=BG, fg=FG,
                 font=self.app.fonts["h2"]).pack(side="left")
        self._where = tk.Label(head, text=str(self.base), bg=BG, fg=FG_FAINT,
                               font=self.app.fonts["small"])
        self._where.pack(side="right")

        body = tk.Frame(pad, bg=BG)
        body.pack(fill="both", expand=True, pady=(12, 0))

        left = tk.Frame(body, bg=BG_ALT, highlightthickness=1,
                        highlightbackground=BORDER)
        left.pack(side="left", fill="both", expand=True)
        lb = tk.Frame(left, bg=BG_ALT)
        lb.pack(fill="x")
        tk.Label(lb, text="存档", bg=BG_ALT, fg=FG_DIM,
                 font=self.app.fonts["small"]).pack(side="left", padx=10, pady=7)
        self._count = tk.Label(lb, text="", bg=BG_ALT, fg=FG_FAINT,
                               font=self.app.fonts["small"])
        self._count.pack(side="right", padx=10)
        tk.Frame(left, bg=BORDER, height=1).pack(fill="x")
        self._wscroll = ScrollFrame(left, bg=BG_ALT)
        self._wscroll.pack(fill="both", expand=True, padx=1, pady=1)

        right = tk.Frame(body, bg=BG_ALT, width=250, highlightthickness=1,
                         highlightbackground=BORDER)
        right.pack(side="left", fill="both", padx=(12, 0))
        right.pack_propagate(False)
        rb = tk.Frame(right, bg=BG_ALT)
        rb.pack(fill="x")
        tk.Label(rb, text="备份", bg=BG_ALT, fg=FG_DIM,
                 font=self.app.fonts["small"]).pack(side="left", padx=10, pady=7)
        tk.Frame(right, bg=BORDER, height=1).pack(fill="x")
        self._bscroll = ScrollFrame(right, bg=BG_ALT)
        self._bscroll.pack(fill="both", expand=True, padx=1, pady=1)

        tools = tk.Frame(pad, bg=BG)
        tools.pack(fill="x", pady=(12, 0))
        self._backup_btn = FlatButton(tools, "备份选中存档", command=self._backup,
                                      kind="primary", height=32, width=118, bg=BG)
        self._backup_btn.pack(side="left")
        self._restore_btn = FlatButton(tools, "恢复最新备份", command=self._restore,
                                       kind="normal", height=32, width=112, bg=BG)
        self._restore_btn.pack(side="left", padx=8)
        self._open_btn = FlatButton(tools, "打开存档目录", command=self._open,
                                    kind="ghost", height=32, width=108, bg=BG)
        self._open_btn.pack(side="left")
        self._del_btn = FlatButton(tools, "删除存档", command=self._delete,
                                   kind="danger", height=32, width=88, bg=BG)
        self._del_btn.pack(side="left", padx=8)
        FlatButton(tools, "刷新", command=self.reload, kind="ghost",
                   height=32, width=64, bg=BG).pack(side="left")
        FlatButton(tools, "关闭", command=self._close, kind="normal",
                   height=32, width=72, bg=BG).pack(side="right")

        self._bar = ProgressBar(pad, height=6)
        self._bar.pack(fill="x", pady=(10, 0))
        self._log = LogPanel(pad, height=6)
        self._log.pack(fill="x", pady=(8, 0))

        self._set_enabled(False)

    def _center(self) -> None:
        self.update_idletasks()
        w, h = 760, 560
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2 - 30}")

    # ------------------------------------------------------------ 数据

    def reload(self) -> None:
        from .. import worlds

        for row in self.rows.values():
            row.destroy()
        self.rows.clear()
        self.selected = None
        try:
            items = worlds.list_worlds(self.base)
        except Exception as exc:                       # noqa: BLE001
            self._log.write(f"读取存档失败：{exc}")
            items = []
        for world in items:
            self._add_row(world)
        self._count.configure(text=f"共 {len(items)} 个")
        if not items:
            tk.Label(self._wscroll.inner, text="还没有存档。进游戏创建世界后回到这里即可备份。",
                     bg=BG_ALT, fg=FG_FAINT, font=self.app.fonts["small"]).pack(pady=30)
        self._wscroll.inner.update_idletasks()
        self._wscroll.scroll_to_top()
        self._reload_backups()
        self._set_enabled(False)

    def _add_row(self, world) -> None:
        row = SelectableRow(self._wscroll.inner, lambda w=world: self._select(w),
                            bg=BG_ALT, pad=9)
        row.pack(fill="x")
        box = tk.Frame(row.inner, bg=BG_ALT)
        box.pack(side="left", fill="both", expand=True)
        tk.Label(box, text=world.name, bg=BG_ALT, fg=FG,
                 font=self.app.fonts["body"]).pack(anchor="w")
        meta = f"{world.size_text()} · {world.mtime_text()}"
        if world.version:
            meta += f" · {world.version}"
        tk.Label(box, text=meta, bg=BG_ALT, fg=FG_FAINT,
                 font=self.app.fonts["small"]).pack(anchor="w")
        row.attach()
        self.rows[world.folder] = row

    def _reload_backups(self) -> None:
        from .. import worlds

        for child in self._bscroll.inner.winfo_children():
            child.destroy()
        try:
            items = worlds.list_backups(self.base)
        except Exception:                              # noqa: BLE001
            items = []
        self._backup_paths = items
        if not items:
            tk.Label(self._bscroll.inner, text="暂无备份", bg=BG_ALT, fg=FG_FAINT,
                     font=self.app.fonts["small"]).pack(pady=24)
            return
        for path in items[:60]:
            row = SelectableRow(self._bscroll.inner, lambda p=path: self._restore(p),
                                bg=BG_ALT, pad=8)
            row.pack(fill="x")
            box = tk.Frame(row.inner, bg=BG_ALT)
            box.pack(side="left", fill="both", expand=True)
            tk.Label(box, text=path.stem, bg=BG_ALT, fg=FG, font=self.app.fonts["small"],
                     wraplength=200, justify="left").pack(anchor="w")
            tk.Label(box, text=f"{path.stat().st_size / 1024:.0f} KB",
                     bg=BG_ALT, fg=FG_FAINT,
                     font=self.app.fonts["small"]).pack(anchor="w")
            row.attach()
        self._bscroll.inner.update_idletasks()
        self._bscroll.scroll_to_top()

    def _select(self, world) -> None:
        self.selected = world
        for key, row in self.rows.items():
            row.set_selected(key == world.folder)
        self._set_enabled(True)

    def _set_enabled(self, value: bool) -> None:
        has = bool(self.selected)
        self._backup_btn.set_enabled(has and not self._busy)
        self._del_btn.set_enabled(has and not self._busy)
        self._restore_btn.set_enabled(bool(getattr(self, "_backup_paths", None))
                                      and not self._busy)

    # ------------------------------------------------------------ 动作

    def _backup(self) -> None:
        from .. import worlds

        if not self.selected:
            return
        world = self.selected
        self._busy = True
        self._set_enabled(False)
        self._bar.set(0)
        self._log.write(f"开始备份「{world.name}」…")

        def work() -> None:
            try:
                path = worlds.backup(world, worlds.backups_dir(self.base),
                                     on_log=self._safe_log,
                                     progress_cb=lambda v: self.app.post(
                                         lambda x=v: self._bar.set(x)))
            except Exception as exc:                   # noqa: BLE001
                self.app.post(lambda: self._done(f"备份失败：{exc}", False))
                return
            self.app.post(lambda: self._done(
                f"已备份到 {path.name}（{path.stat().st_size / 1024:.0f} KB）", True))

        threading.Thread(target=work, daemon=True).start()

    def _restore(self, path: Path | None = None) -> None:
        from .. import worlds

        target = path or (self._backup_paths[0] if getattr(self, "_backup_paths", None) else None)
        if not target:
            self.app.notify("还没有可恢复的备份", "info")
            return
        if not messagebox.askyesno("恢复存档", f"把备份「{Path(target).stem}」恢复到存档目录？\n"
                                              "同名世界会自动改名，不会覆盖已有世界。", parent=self):
            return
        ok, msg = worlds.restore(Path(target), self.base)
        self._log.write(msg)
        self.app.notify(msg, "ok" if ok else "err")
        self.reload()

    def _delete(self) -> None:
        from .. import worlds

        if not self.selected:
            return
        world = self.selected
        if not messagebox.askyesno("删除存档", f"永久删除「{world.name}」？\n此操作不可恢复。",
                                   parent=self):
            return
        ok, msg = worlds.delete(world)
        self._log.write(msg)
        self.app.notify(msg, "ok" if ok else "err")
        self.reload()

    def _open(self) -> None:
        from .. import worlds

        try:
            self.base.mkdir(parents=True, exist_ok=True)
            worlds.open_folder(self.base)
        except Exception as exc:                       # noqa: BLE001
            self.app.notify(f"打不开目录：{exc}", "err")

    def _safe_log(self, msg: str) -> None:
        self.app.post(lambda: self._log.write(msg))

    def _done(self, msg: str, ok: bool) -> None:
        self._busy = False
        self._bar.set(1 if ok else 0)
        self._log.write(msg)
        self.app.notify(msg, "ok" if ok else "err")
        self.reload()

    def _close(self) -> None:
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
