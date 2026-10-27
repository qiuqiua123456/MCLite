"""下载页：拉取版本清单、筛选、一键安装。"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox
from typing import Any

from ..downloader import Progress, fetch_json, human_size, human_speed
from ..installer import Installer
from ..versionmeta import VERSION_MANIFEST, VersionSummary, parse_manifest
from . import images
from .theme import (
    ACCENT, BG, BG_ALT, BG_HOVER, BORDER, DANGER, FG, FG_DIM, FG_FAINT,
    SUCCESS, WARN, FlatButton, ScrollFrame,
)
from .widgets import LogPanel, Page, ProgressBar, SelectableRow

FILTERS = [
    ("全部",   None),
    ("正式版", "release"),
    ("快照",   "snapshot"),
    ("远古版", "old"),
]


class InstallPage(Page):
    title = "下载"

    def build(self) -> None:
        self._all: list[VersionSummary] = []
        self._filter = "release"
        self._rows: dict[str, SelectableRow] = {}
        self._selected: VersionSummary | None = None
        self._installing = False
        self._installer: Installer | None = None
        self._loading = False
        self._last_progress = None
        self._tick_job = None

        root = tk.Frame(self, bg=BG)
        root.pack(fill="both", expand=True, padx=24, pady=(20, 12))

        head = tk.Frame(root, bg=BG)
        head.pack(fill="x")
        tk.Label(head, text="下载游戏版本", bg=BG, fg=FG,
                 font=self.app.fonts["h1"]).pack(side="left")
        self._count_label = tk.Label(head, text="", bg=BG, fg=FG_FAINT,
                                     font=self.app.fonts["small"])
        self._count_label.pack(side="right", pady=(8, 0))

        # ---------------- 工具条
        tools = tk.Frame(root, bg=BG)
        tools.pack(fill="x", pady=(12, 10))

        self._search_var = tk.StringVar()
        search = tk.Entry(tools, textvariable=self._search_var, bg=BG_ALT, fg=FG,
                          insertbackground=FG, bd=0, highlightthickness=1,
                          highlightbackground=BORDER, highlightcolor=ACCENT,
                          font=self.app.fonts["body"], width=22)
        search.pack(side="left", ipady=5)
        self._search_entry = search
        self._ph = tk.Label(tools, text="搜索版本号，如 1.20.1", bg=BG_ALT,
                            fg=FG_FAINT, bd=0, font=self.app.fonts["small"])
        self._ph.place(in_=search, x=7, rely=0.5, anchor="w")
        search.bind("<FocusIn>", lambda _e: self._ph.place_forget())
        search.bind("<FocusOut>", self._on_search_blur)
        self._search_var.trace_add("write", lambda *_a: self._on_search_typed())

        self._filter_buttons: dict[str, FlatButton] = {}
        for label, kind in FILTERS:
            btn = FlatButton(tools, label, command=lambda k=kind: self._set_filter(k),
                             kind="primary" if kind == self._filter else "ghost",
                             height=30, width=64,
                             font=self.app.fonts["small"], bg=BG)
            btn.pack(side="left", padx=(8, 0))
            self._filter_buttons[label] = btn

        FlatButton(tools, "获取版本清单", command=lambda: self.load_manifest(force=True),
                   kind="normal", height=30, width=110,
                   font=self.app.fonts["small"], bg=BG).pack(side="right")

        # ---------------- 主体
        body = tk.Frame(root, bg=BG)
        body.pack(fill="both", expand=True)

        left = tk.Frame(body, bg=BG_ALT, width=380)
        left.pack(side="left", fill="both", expand=False)
        left.pack_propagate(False)
        tk.Frame(left, bg=BORDER, height=1).pack(fill="x")
        self._scroll = ScrollFrame(left, bg=BG_ALT)
        self._scroll.pack(fill="both", expand=True)
        self._empty_hint = tk.Label(self._scroll.inner, text="点击右上角「获取版本清单」",
                                    bg=BG_ALT, fg=FG_FAINT, font=self.app.fonts["body"])
        self._empty_hint.pack(pady=(24, 6))
        art = images.load(self, "empty-search")
        if art is not None:
            cap = tk.Label(self._scroll.inner, image=art, bg=BG_ALT, bd=0)
            cap.image = art
            cap.pack(pady=(0, 30))

        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(18, 0))

        card = tk.Frame(right, bg=BG_ALT)
        card.pack(fill="x")
        info = tk.Frame(card, bg=BG_ALT, padx=18, pady=16)
        info.pack(fill="x")
        self._big_name = tk.Label(info, text="未选择版本", bg=BG_ALT, fg=FG,
                                  font=("Segoe UI", 18, "bold"), anchor="w")
        self._big_name.pack(fill="x")
        self._big_sub = tk.Label(info, text="从左侧选择一个版本", bg=BG_ALT, fg=FG_DIM,
                                 anchor="w", justify="left", font=self.app.fonts["small"])
        self._big_sub.pack(fill="x", pady=(6, 0))

        tk.Frame(card, bg=BORDER, height=1).pack(fill="x", padx=18)
        act = tk.Frame(card, bg=BG_ALT, padx=18, pady=14)
        act.pack(fill="x")
        self._install_btn = FlatButton(act, "下载并安装", command=self.start_install,
                                       kind="primary", height=38, width=140,
                                       font=("Microsoft YaHei UI", 10, "bold"), bg=BG_ALT)
        self._install_btn.pack(side="left")
        self._install_btn.set_enabled(False)
        self._cancel_btn = FlatButton(act, "取消", command=self.cancel_install,
                                      kind="danger", height=38, width=80, bg=BG_ALT)
        self._cancel_btn.pack(side="left", padx=8)
        self._cancel_btn.set_enabled(False)
        self._loader_btn = FlatButton(act, "安装加载器…", command=self.open_loader_dialog,
                                      kind="normal", height=38, width=120, bg=BG_ALT)
        self._loader_btn.pack(side="left")
        self._loader_btn.set_enabled(False)

        # 进度
        prog = tk.Frame(right, bg=BG_ALT)
        prog.pack(fill="x", pady=(14, 0))
        ph = tk.Frame(prog, bg=BG_ALT, padx=18, pady=12)
        ph.pack(fill="x")
        self._progress = ProgressBar(ph, height=6)
        self._progress.pack(fill="x")
        self._prog_label = tk.Label(ph, text="", bg=BG_ALT, fg=FG_DIM, anchor="w",
                                    font=self.app.fonts["small"])
        self._prog_label.pack(fill="x", pady=(6, 0))

        # 日志
        log_card = tk.Frame(right, bg=BG_ALT)
        log_card.pack(fill="both", expand=True, pady=(14, 0))
        lb = tk.Frame(log_card, bg=BG_ALT, height=32)
        lb.pack(fill="x")
        lb.pack_propagate(False)
        tk.Label(lb, text="安装日志", bg=BG_ALT, fg=FG_DIM,
                 font=self.app.fonts["small"]).pack(side="left", padx=12, pady=7)
        FlatButton(lb, "清空", command=lambda: self._log.clear(), kind="ghost",
                   height=22, font=self.app.fonts["small"], bg=BG_ALT,
                   width=56).pack(side="right", padx=8, pady=5)
        tk.Frame(log_card, bg=BORDER, height=1).pack(fill="x")
        self._log = LogPanel(log_card, height=7)
        self._log.pack(fill="both", expand=True)

        self.after(200, self.load_manifest)

    # ------------------------------------------------------------ 清单

    def on_show(self) -> None:
        self.load_manifest()

    def load_manifest(self, force: bool = False) -> None:
        if self._loading:
            return
        if self._all and not force:
            return
        self._loading = True
        self._log.write("正在获取版本清单…")
        source = self.app.cfg.get("download_source") or "official"

        def work():
            try:
                data = fetch_json(VERSION_MANIFEST, source=source)
                versions = parse_manifest(data)
                self.post(lambda: self._on_manifest(versions))
            except Exception as exc:                 # noqa: BLE001
                msg = f"{type(exc).__name__}: {exc}"
                self.post(lambda: self._on_manifest_error(msg))

        threading.Thread(target=work, daemon=True).start()

    def _on_manifest(self, versions: list[VersionSummary]) -> None:
        self._loading = False
        self._all = versions
        self._log.write(f"获取成功，共 {len(versions)} 个版本", "ok")
        self._render_list()

    def _on_manifest_error(self, msg: str) -> None:
        self._loading = False
        self._log.write(f"获取失败：{msg}", "err")
        self.app.notify("获取版本清单失败，请检查网络或下载源设置", "err")

    def _set_filter(self, kind: str | None) -> None:
        self._filter = kind
        for label, k in FILTERS:
            btn = self._filter_buttons[label]
            btn.kind = "primary" if k == kind else "ghost"
            btn._draw()
        self._render_list()

    def _on_search_typed(self) -> None:
        self._render_list()

    def _on_search_blur(self, _e=None) -> None:
        if not self._search_var.get().strip():
            try:
                self._ph.place(in_=self._search_entry, x=7, rely=0.5, anchor="w")
            except tk.TclError:
                pass

    def _render_list(self) -> None:
        for w in self._scroll.inner.winfo_children():
            w.destroy()
        self._rows.clear()
        self._empty_hint = None

        query = self._search_var.get().strip().lower()
        shown = []
        for v in self._all:
            if self._filter == "old":
                if v.type not in ("old_beta", "old_alpha"):
                    continue
            elif self._filter and v.type != self._filter:
                continue
            if query and query not in v.id.lower():
                continue
            shown.append(v)

        self._count_label.configure(text=f"共 {len(self._all)} 个版本，当前显示 {len(shown)} 个")

        if not shown:
            art = images.load(self, "empty-search") if not self._all else None
            if art is not None:
                box = tk.Frame(self._scroll.inner, bg=BG_ALT)
                box.pack(fill="x", pady=(24, 6))
                cap = tk.Label(box, image=art, bg=BG_ALT, bd=0)
                cap.image = art
                cap.pack()
                tk.Label(box, text="点击右上角「获取版本清单」", bg=BG_ALT, fg=FG_FAINT,
                         font=self.app.fonts["body"]).pack(pady=(10, 0))
            else:
                tk.Label(self._scroll.inner, text="没有匹配的版本",
                         bg=BG_ALT, fg=FG_FAINT, font=self.app.fonts["body"]).pack(pady=40)
            return

        for v in shown[:400]:
            self._add_row(v)

    def _add_row(self, v: VersionSummary) -> None:
        row = SelectableRow(self._scroll.inner,
                            on_click=lambda ver=v: self._select(ver), bg=BG_ALT, pad=9)
        row.pack(fill="x")
        color = {"release": SUCCESS, "snapshot": WARN}.get(v.type, FG_FAINT)
        stripe = tk.Frame(row.inner, bg=color, width=3, height=30)
        stripe.pack(side="left", fill="y", padx=(0, 10))

        box = tk.Frame(row.inner, bg=BG_ALT)
        box.pack(side="left", fill="both", expand=True)
        tk.Label(box, text=v.id, bg=BG_ALT, fg=FG, anchor="w",
                 font=self.app.fonts["body"]).pack(fill="x")
        type_cn = {"release": "正式版", "snapshot": "快照",
                   "old_beta": "远古 Beta", "old_alpha": "远古 Alpha"}.get(v.type, v.type)
        date = (v.release_time or "")[:10]
        tk.Label(box, text=f"{type_cn}   {date}", bg=BG_ALT, fg=FG_FAINT,
                 anchor="w", font=self.app.fonts["small"]).pack(fill="x")
        row.attach()
        self._rows[v.id] = row

    def _select(self, v: VersionSummary) -> None:
        self._selected = v
        for k, row in self._rows.items():
            row.set_selected(k == v.id)
        self._big_name.configure(text=v.id)
        type_cn = {"release": "正式版", "snapshot": "快照",
                   "old_beta": "远古 Beta", "old_alpha": "远古 Alpha"}.get(v.type, v.type)
        self._big_sub.configure(text=f"{type_cn}   ·   发布于 {(v.release_time or '')[:19].replace('T', ' ')}")
        self._install_btn.set_enabled(not self._installing)
        self._loader_btn.set_enabled(not self._installing)

    # ------------------------------------------------------------ 加载器

    def open_loader_dialog(self) -> None:
        if self._installing or not self._selected:
            return
        from .loader_dialog import LoaderDialog

        dlg = LoaderDialog(self.app, self._selected.id, on_done=self._on_loader_done)
        self.app.notify(f"选择要安装到 {self._selected.id} 的加载器", "info")
        dlg.grab_set()
        try:
            self.wait_window(dlg)
        except tk.TclError:
            pass

    def _on_loader_done(self, vid: str) -> None:
        home = self.app._pages.get("home")
        if home is not None:
            home.reload_versions()

    # ------------------------------------------------------------ 安装

    def start_install(self) -> None:
        if self._installing or not self._selected:
            return
        v = self._selected
        game_dir = self.app.cfg.game_dir
        source = self.app.cfg.get("download_source") or "official"
        threads = int(self.app.cfg.get("download_threads") or 16)

        self._installing = True
        self._install_btn.set_enabled(False)
        self._cancel_btn.set_enabled(True)
        self._progress.set(0)
        self._prog_label.configure(text="准备中…")
        self._last_progress = None
        self._tick_progress()
        self._log.write(f"开始安装 {v.id} → {game_dir}")
        self._log.write(f"下载源：{'BMCLAPI' if source == 'bmclapi' else '官方'}，线程 {threads}")

        installer = Installer(game_dir, source=source, threads=threads,
                              log=lambda m: self._log.write(m))
        self._installer = installer

        def work():
            try:
                ok, msg = installer.install(v.id, v.url, progress_cb=self._on_progress)
            except Exception as exc:                 # noqa: BLE001
                ok, msg = False, f"{type(exc).__name__}: {exc}"
            self.post(lambda: self._on_install_done(ok, msg, v.id))

        threading.Thread(target=work, daemon=True).start()

    def _on_progress(self, p: Progress) -> None:
        """下载线程高频回调：只记住最新的进度对象，由主线程节流刷新。"""
        self._last_progress = p

    def _tick_progress(self) -> None:
        p = self._last_progress
        if p is not None and self._installing:
            try:
                pct, current, speed = p.snapshot()
                self._progress.set(pct)
                self._prog_label.configure(
                    text=f"{pct * 100:5.1f}%   {p.done_files}/{p.total_files} 个文件   "
                         f"{human_size(p.done_bytes)} / {human_size(p.total_bytes)}   "
                         f"{human_speed(speed)}   {current}")
                self.app.set_status(f"下载中 {pct * 100:.1f}%", human_speed(speed))
            except (tk.TclError, AttributeError):
                pass
        if self._installing:
            try:
                self._tick_job = self.after(120, self._tick_progress)
            except tk.TclError:
                pass

    def cancel_install(self) -> None:
        if self._installer:
            self._installer.cancelled.set()
            self._log.write("正在取消…", "warn")
            self._cancel_btn.set_enabled(False)

    def _on_install_done(self, ok: bool, msg: str, vid: str) -> None:
        self._installing = False
        self._installer = None
        self._install_btn.set_enabled(self._selected is not None)
        self._loader_btn.set_enabled(self._selected is not None)
        self._cancel_btn.set_enabled(False)
        self.app.set_status("就绪")
        if ok:
            self._progress.set(1.0)
            self._prog_label.configure(text="安装完成")
            self._log.write(f"{vid} 安装完成", "ok")
            self.app.notify(f"{vid} 安装完成", "ok")
            home = self.app._pages.get("home")
            if home is not None:
                home.reload_versions()
        elif msg == "用户取消" or "已取消" in msg:
            self._prog_label.configure(text="已取消")
            self._log.write(f"已取消安装 {vid}", "warn")
            self.app.notify("已取消安装", "warn")
        else:
            self._prog_label.configure(text="安装失败")
            self._log.write(f"安装失败：{msg}", "err")
            self.app.notify("安装失败：" + msg[:60], "err")
            messagebox.showerror("安装失败", msg, parent=self)
