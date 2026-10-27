"""整合包：本地导入进度窗口 + Modrinth 整合包市场。

整合包（``.mrpack``）装完之后会成为一个**独立版本**，配合实例隔离，
它的 mods / config / 存档都在自己的目录里，不会污染原版。
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from .. import modpack
from .theme import (
    BG, BG_ALT, BORDER, FG, FG_DIM, FG_FAINT, SUCCESS, WARN,
    FlatButton, ScrollFrame,
)
from .widgets import LogPanel, ProgressBar, SelectableRow


class PackInstallDialog(tk.Toplevel):
    """装一个本地 .mrpack，显示日志和进度。"""

    def __init__(self, app, path: Path, on_done=None, base_version: str = ""):
        super().__init__(app)
        self.app = app
        self.path = Path(path)
        self.base_version = base_version or ""
        self._on_done = on_done
        self._cancel = False
        self._finished = False
        self.title("安装整合包")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.geometry("660x470")
        self._build()
        self._center()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(120, self._start)

    # ------------------------------------------------------------ 布局

    def _build(self) -> None:
        pad = tk.Frame(self, bg=BG, padx=20, pady=16)
        pad.pack(fill="both", expand=True)

        tk.Label(pad, text="安装整合包", bg=BG, fg=FG,
                 font=self.app.fonts["h1"], anchor="w").pack(fill="x")
        self._sub = tk.Label(pad, text=self.path.name, bg=BG, fg=FG_FAINT,
                             font=self.app.fonts["small"], anchor="w")
        self._sub.pack(fill="x", pady=(2, 10))

        self._bar = ProgressBar(pad, height=10)
        self._bar.pack(fill="x")
        self._status = tk.Label(pad, text="准备中…", bg=BG, fg=FG_DIM,
                                font=self.app.fonts["small"], anchor="w")
        self._status.pack(fill="x", pady=(6, 10))

        self._log = LogPanel(pad, height=14)
        self._log.pack(fill="both", expand=True)
        self._log.write(f"整合包：{self.path}")

        bottom = tk.Frame(pad, bg=BG)
        bottom.pack(fill="x", pady=(10, 0))
        self._close_btn = FlatButton(bottom, "关闭", command=self._close, kind="ghost",
                                     height=32, width=90, bg=BG)
        self._close_btn.pack(side="right")
        self._cancel_btn = FlatButton(bottom, "取消安装", command=self._do_cancel,
                                      kind="danger", height=32, width=100, bg=BG)
        self._cancel_btn.pack(side="right", padx=(0, 8))

    def _center(self) -> None:
        self.update_idletasks()
        try:
            px, py = self.app.winfo_rootx(), self.app.winfo_rooty()
            pw, ph = self.app.winfo_width(), self.app.winfo_height()
            w, h = self.winfo_width(), self.winfo_height()
            self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 3}")
        except tk.TclError:
            pass

    # ------------------------------------------------------------ 安装

    def _start(self) -> None:
        import threading

        def progress(p) -> None:
            def show():
                try:
                    pct = p.percent()
                    self._bar.set(pct / 100.0 if pct <= 100 else 1.0)
                    self._status.configure(
                        text=f"{p.done_files}/{p.total_files} 个文件   "
                             f"{p.done_bytes / 1048576:.1f} MB   {p.speed / 1048576:.2f} MB/s")
                except tk.TclError:
                    pass
            self.app.post(show)

        def work() -> None:
            try:
                from .. import packdetect
                vid = packdetect.install_any(
                    self.path, self.app.cfg.game_dir,
                    base_version=self.base_version,
                    on_log=lambda m: self._log.write(m),
                    progress_cb=progress,
                    cancel=lambda: self._cancel)
            except Exception as exc:                 # noqa: BLE001
                self.app.post(lambda: self._finish(False, str(exc)))
                return
            self.app.post(lambda: self._finish(True, vid))

        threading.Thread(target=work, daemon=True).start()

    def _finish(self, ok: bool, msg: str) -> None:
        self._finished = True
        try:
            self._cancel_btn.set_enabled(False)
            if ok:
                self._bar.set(1.0)
                self._status.configure(text=f"安装完成：{msg}", fg=SUCCESS)
                self._log.write(f"✔ 整合包已装成版本「{msg}」，到「开始」页选中它就能玩", "ok")
                self._sub.configure(text=f"实例版本：{msg}")
                if self._on_done:
                    self._on_done(msg)
            else:
                self._status.configure(text="安装失败", fg=WARN)
                self._log.write(f"✘ {msg}", "err")
        except tk.TclError:
            pass

    def _do_cancel(self) -> None:
        self._cancel = True
        self._cancel_btn.set_enabled(False)
        self._log.write("正在取消…", "warn")

    def _close(self) -> None:
        if not self._finished:
            if not messagebox.askyesno("确认关闭", "安装还没结束，关闭窗口会中断安装。继续？",
                                       parent=self):
                return
            self._cancel = True
        self.destroy()


class PackMarketDialog(tk.Toplevel):
    """从 Modrinth 找整合包，下载后交给 PackInstallDialog 安装。"""

    def __init__(self, app, on_done=None):
        super().__init__(app)
        self.app = app
        self._on_done = on_done
        self._busy = False
        self._projects = []
        self._selected = None
        self._versions = []
        self._rows: dict[str, SelectableRow] = {}
        self._vrows: dict[str, SelectableRow] = {}
        self.title("整合包市场")
        self.configure(bg=BG)
        self.geometry("920x600")
        self._build()
        self._center()
        self.after(150, lambda: self._search())

    def _center(self) -> None:
        self.update_idletasks()
        try:
            px, py = self.app.winfo_rootx(), self.app.winfo_rooty()
            pw, ph = self.app.winfo_width(), self.app.winfo_height()
            w, h = self.winfo_width(), self.winfo_height()
            self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 3}")
        except tk.TclError:
            pass

    # ------------------------------------------------------------ 布局

    def _build(self) -> None:
        pad = tk.Frame(self, bg=BG, padx=20, pady=16)
        pad.pack(fill="both", expand=True)

        head = tk.Frame(pad, bg=BG)
        head.pack(fill="x")
        tk.Label(head, text="整合包市场", bg=BG, fg=FG,
                 font=self.app.fonts["h1"]).pack(side="left")
        tk.Label(head, text="数据来自 Modrinth", bg=BG, fg=FG_FAINT,
                 font=self.app.fonts["small"]).pack(side="left", padx=(10, 0), pady=(6, 0))

        row = tk.Frame(pad, bg=BG)
        row.pack(fill="x", pady=(12, 10))
        self._query = tk.Entry(row, bg=BG_ALT, fg=FG, insertbackground=FG, bd=0,
                               highlightthickness=1, highlightbackground=BORDER,
                               highlightcolor=BORDER, font=self.app.fonts["body"])
        self._query.pack(side="left", fill="x", expand=True, ipady=6)
        self._query.bind("<Return>", lambda _e: self._search())
        self._ver = tk.Entry(row, bg=BG_ALT, fg=FG, insertbackground=FG, bd=0,
                             highlightthickness=1, highlightbackground=BORDER,
                             highlightcolor=BORDER, font=self.app.fonts["body"], width=10)
        self._ver.pack(side="left", padx=(8, 0), ipady=6)
        self._search_btn = FlatButton(row, "搜索", command=self._search, kind="primary",
                                      height=32, width=80, bg=BG)
        self._search_btn.pack(side="left", padx=(8, 0))
        self._local_btn = FlatButton(row, "导入本地 .mrpack…", command=self._import_local,
                                     kind="ghost", height=32, width=150, bg=BG)
        self._local_btn.pack(side="left", padx=(8, 0))

        body = tk.Frame(pad, bg=BG)
        body.pack(fill="both", expand=True)

        left = tk.Frame(body, bg=BG_ALT)
        left.pack(side="left", fill="both", expand=True)
        self._count = tk.Label(left, text="搜索中…", bg=BG_ALT, fg=FG_FAINT,
                               font=self.app.fonts["small"], anchor="w")
        self._count.pack(fill="x", padx=12, pady=(8, 4))
        self._lscroll = ScrollFrame(left, bg=BG_ALT)
        self._lscroll.pack(fill="both", expand=True)

        right = tk.Frame(body, bg=BG_ALT, width=330)
        right.pack(side="left", fill="both", padx=(12, 0))
        right.pack_propagate(False)
        self._vtitle = tk.Label(right, text="版本", bg=BG_ALT, fg=FG_DIM,
                                font=self.app.fonts["small"], anchor="w")
        self._vtitle.pack(fill="x", padx=12, pady=(8, 4))
        self._rscroll = ScrollFrame(right, bg=BG_ALT)
        self._rscroll.pack(fill="both", expand=True)

        bottom = tk.Frame(pad, bg=BG)
        bottom.pack(fill="x", pady=(10, 0))
        self._status = tk.Label(bottom, text="", bg=BG, fg=FG_DIM,
                                font=self.app.fonts["small"], anchor="w")
        self._status.pack(side="left", fill="x", expand=True)
        self._install_btn = FlatButton(bottom, "下载并安装", command=self._install,
                                       kind="primary", height=34, width=120, bg=BG)
        self._install_btn.pack(side="right")
        self._install_btn.set_enabled(False)

    # ------------------------------------------------------------ 搜索

    def _set_status(self, text: str, color: str = FG_DIM) -> None:
        try:
            self._status.configure(text=text, fg=color)
        except tk.TclError:
            pass

    def _search(self) -> None:
        if self._busy:
            return
        import threading

        from .. import modrinth
        query = self._query.get().strip()
        version = self._ver.get().strip()
        self._busy = True
        self._count.configure(text="搜索中…")
        self._set_status("正在搜索整合包…")

        def work() -> None:
            try:
                items, total = modrinth.search(query, version, "", limit=25,
                                               project_type="modpack")
            except Exception as exc:                 # noqa: BLE001
                self.app.post(lambda: self._on_error(str(exc)))
                return
            self.app.post(lambda: self._on_results(items, total))

        threading.Thread(target=work, daemon=True).start()

    def _on_error(self, msg: str) -> None:
        self._busy = False
        self._count.configure(text="搜索失败")
        self._set_status(f"搜索失败：{msg}", WARN)

    def _on_results(self, items, total: int) -> None:
        self._busy = False
        self._projects = items
        self._selected = None
        self._versions = []
        self._rows.clear()
        self._vrows.clear()
        for w in self._lscroll.inner.winfo_children():
            w.destroy()
        for w in self._rscroll.inner.winfo_children():
            w.destroy()
        self._install_btn.set_enabled(False)
        self._count.configure(text=f"搜索结果（{total} 个，显示 {len(items)} 个）")
        self._vtitle.configure(text="版本")
        if not items:
            tk.Label(self._lscroll.inner, text="没找到整合包，换个关键词试试",
                     bg=BG_ALT, fg=FG_DIM, font=self.app.fonts["body"]).pack(pady=40)
            return
        for p in items:
            row = SelectableRow(self._lscroll.inner,
                                on_click=lambda x=p: self._pick(x), bg=BG_ALT, pad=8)
            row.pack(fill="x")
            box = tk.Frame(row.inner, bg=BG_ALT)
            box.pack(side="left", fill="both", expand=True)
            tk.Label(box, text=p.title, bg=BG_ALT, fg=FG, anchor="w",
                     font=self.app.fonts["body"]).pack(fill="x")
            desc = p.description
            if len(desc) > 60:
                desc = desc[:58] + "…"
            tk.Label(box, text=desc, bg=BG_ALT, fg=FG_FAINT, anchor="w",
                     font=self.app.fonts["small"]).pack(fill="x")
            tk.Label(row.inner, text=p.downloads_label, bg=BG_ALT, fg=FG_FAINT,
                     font=self.app.fonts["small"]).pack(side="right", padx=(0, 10))
            row.attach()
            self._rows[p.project_id] = row
        self._lscroll.inner.update_idletasks()
        self.after_idle(self._lscroll.scroll_to_top)

    def _pick(self, project) -> None:
        self._selected = project
        for k, row in self._rows.items():
            row.set_selected(k == project.project_id)
        self._vtitle.configure(text=f"{project.title} 的版本")
        for w in self._rscroll.inner.winfo_children():
            w.destroy()
        self._vrows.clear()
        self._versions = []
        self._install_btn.set_enabled(False)
        self._set_status("正在读取版本…")
        version = self._ver.get().strip()

        import threading

        from .. import modrinth

        def work() -> None:
            try:
                vers = modrinth.versions(project.project_id, version, "")
            except Exception as exc:                 # noqa: BLE001
                self.app.post(lambda: self._on_error(str(exc)))
                return
            self.app.post(lambda: self._on_versions(vers))

        threading.Thread(target=work, daemon=True).start()

    def _on_versions(self, vers) -> None:
        self._versions = vers
        if not vers:
            tk.Label(self._rscroll.inner, text="没有可下载的版本", bg=BG_ALT, fg=FG_DIM,
                     font=self.app.fonts["small"]).pack(pady=20)
            self._set_status("这个整合包没有可用版本")
            return
        for v in vers[:40]:
            row = SelectableRow(self._rscroll.inner, on_click=lambda x=v: self._pick_version(x),
                                bg=BG_ALT, pad=7)
            row.pack(fill="x")
            box = tk.Frame(row.inner, bg=BG_ALT)
            box.pack(side="left", fill="both", expand=True)
            tk.Label(box, text=v.version_name or v.name, bg=BG_ALT, fg=FG, anchor="w",
                     font=self.app.fonts["small"]).pack(fill="x")
            games = "、".join(v.game_versions[:3]) if v.game_versions else "?"
            tk.Label(box, text=games, bg=BG_ALT, fg=FG_FAINT, anchor="w",
                     font=self.app.fonts["small"]).pack(fill="x")
            size = f"{v.files[0].size / 1048576:.1f} MB" if v.files else ""
            tk.Label(row.inner, text=size, bg=BG_ALT, fg=FG_FAINT,
                     font=self.app.fonts["small"]).pack(side="right", padx=(0, 8))
            row.attach()
            self._vrows[v.id] = row
        self._rscroll.inner.update_idletasks()
        self.after_idle(self._rscroll.scroll_to_top)
        self._set_status(f"共 {len(vers)} 个版本，选一个再点「下载并安装」")

    def _pick_version(self, version) -> None:
        self._selected_version = version
        for k, row in self._vrows.items():
            row.set_selected(k == version.id)
        self._install_btn.set_enabled(True)
        fname = version.files[0].filename if version.files else ""
        self._set_status(f"已选择 {version.version_name}   {fname}")

    # ------------------------------------------------------------ 安装

    def _install(self) -> None:
        version = getattr(self, "_selected_version", None)
        if version is None or not version.files:
            return
        import tempfile
        import threading

        from .. import modrinth
        from ..downloader import Downloader, DownloadTask

        f = modrinth.primary_file(version) or version.files[0]
        temp = Path(tempfile.gettempdir()) / "MCLite" / "packs"
        temp.mkdir(parents=True, exist_ok=True)
        dest = temp / (f.filename or "pack.mrpack")
        self._install_btn.set_enabled(False)
        self._set_status(f"正在下载 {f.filename} …")

        def work() -> None:
            task = DownloadTask(url=f.url, dest=dest, sha1=f.sha1 or None,
                                size=f.size or None)
            dl = Downloader(threads=4)
            ok, bad = dl.run([task], source="official")
            if not ok or bad:
                self.app.post(lambda: self._set_status("整合包下载失败", WARN))
                self.app.post(lambda: self._install_btn.set_enabled(True))
                return
            self.app.post(lambda: self._start_install(dest))

        threading.Thread(target=work, daemon=True).start()

    def _base_version(self) -> str:
        home = getattr(self.app, "_pages", {}).get("home")
        return str(getattr(home, "_selected", "") or "")

    def _start_install(self, path: Path) -> None:
        self.destroy()
        dlg = PackInstallDialog(self.app, path, on_done=self._on_done,
                                base_version=self._base_version())
        try:
            dlg.grab_set()
        except tk.TclError:
            pass

    def _import_local(self) -> None:
        files = filedialog.askopenfilenames(
            parent=self, title="选择整合包",
            filetypes=[("整合包", "*.mrpack *.zip"), ("所有文件", "*.*")])
        if not files:
            return
        self.destroy()
        dlg = PackInstallDialog(self.app, Path(files[0]), on_done=self._on_done,
                                base_version=self._base_version())
        try:
            dlg.grab_set()
        except tk.TclError:
            pass
