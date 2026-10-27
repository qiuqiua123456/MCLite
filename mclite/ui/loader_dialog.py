"""加载器安装对话框：给某个原版版本装 Fabric / Forge / NeoForge。"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox

from .. import loaders
from ..java import detect_all, pick_for_version
from .theme import (
    ACCENT, BG, BG_ALT, BORDER, DANGER, FG, FG_DIM, FG_FAINT, SUCCESS,
    FlatButton, ScrollFrame,
)
from .widgets import LogPanel, ProgressBar, SelectableRow

TABS = [("fabric", "Fabric"), ("quilt", "Quilt"), ("forge", "Forge"),
        ("neoforge", "NeoForge")]

WIN_W, WIN_H = 780, 620


class LoaderDialog(tk.Toplevel):
    def __init__(self, app, mc_version: str, on_done=None) -> None:
        super().__init__(app)
        self.app = app
        self.mc_version = mc_version
        self._on_done = on_done

        self.title(f"安装加载器 · {mc_version}")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(app)
        self.geometry(f"{WIN_W}x{WIN_H}")
        self._center()

        self._kind = "fabric"
        self._versions: list[loaders.LoaderVersion] = []
        self._selected: loaders.LoaderVersion | None = None
        self._rows: dict[str, SelectableRow] = {}
        self._installing = False
        self._cancel = threading.Event()
        self._pulse = 0.0

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Escape>", lambda _e: self._on_close())
        self.after(120, lambda: self._load("fabric"))

    # ------------------------------------------------------------ 基础

    def post(self, fn) -> None:
        """后台线程回调统一丢回主线程。"""
        self.app.post(fn)

    def _center(self) -> None:
        self.update_idletasks()
        px, py = self.app.winfo_rootx(), self.app.winfo_rooty()
        pw, ph = self.app.winfo_width(), self.app.winfo_height()
        self.geometry(f"{WIN_W}x{WIN_H}+{px + max(0, (pw - WIN_W) // 2)}"
                      f"+{py + max(0, (ph - WIN_H) // 2)}")

    # ------------------------------------------------------------ 布局

    def _build(self) -> None:
        root = tk.Frame(self, bg=BG)
        root.pack(fill="both", expand=True, padx=20, pady=16)

        head = tk.Frame(root, bg=BG)
        head.pack(fill="x")
        tk.Label(head, text=f"给 {self.mc_version} 安装模组加载器", bg=BG, fg=FG,
                 font=self.app.fonts["h2"]).pack(side="left")
        tk.Label(head, text="装好后在「开始」页选择新版本启动", bg=BG, fg=FG_FAINT,
                 font=self.app.fonts["small"]).pack(side="right", pady=(6, 0))

        tabs = tk.Frame(root, bg=BG)
        tabs.pack(fill="x", pady=(12, 10))
        self._tab_buttons: dict[str, FlatButton] = {}
        for key, label in TABS:
            btn = FlatButton(tabs, label, command=lambda k=key: self._load(k),
                             kind="primary" if key == self._kind else "ghost",
                             height=30, width=92, font=self.app.fonts["body"], bg=BG)
            btn.pack(side="left", padx=(0, 8))
            self._tab_buttons[key] = btn

        body = tk.Frame(root, bg=BG)
        body.pack(fill="both", expand=True)

        left = tk.Frame(body, bg=BG_ALT, width=300)
        left.pack(side="left", fill="both", expand=False)
        left.pack_propagate(False)
        self._list_hint = tk.Label(left, text="正在获取版本列表…", bg=BG_ALT, fg=FG_FAINT,
                                   font=self.app.fonts["small"], anchor="w")
        self._list_hint.pack(fill="x", padx=12, pady=(10, 6))
        tk.Frame(left, bg=BORDER, height=1).pack(fill="x")
        self._scroll = ScrollFrame(left, bg=BG_ALT)
        self._scroll.pack(fill="both", expand=True)

        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(16, 0))

        card = tk.Frame(right, bg=BG_ALT)
        card.pack(fill="x")
        info = tk.Frame(card, bg=BG_ALT, padx=16, pady=14)
        info.pack(fill="x")
        self._big_name = tk.Label(info, text="未选择版本", bg=BG_ALT, fg=FG,
                                  font=("Segoe UI", 15, "bold"), anchor="w")
        self._big_name.pack(fill="x")
        self._big_sub = tk.Label(info, text="从左边选一个加载器版本", bg=BG_ALT, fg=FG_DIM,
                                 anchor="w", justify="left", font=self.app.fonts["small"])
        self._big_sub.pack(fill="x", pady=(4, 0))

        act = tk.Frame(card, bg=BG_ALT, padx=16, pady=12)
        act.pack(fill="x")
        self._install_btn = FlatButton(act, "开始安装", command=self._install,
                                       kind="primary", height=36, width=120,
                                       font=("Microsoft YaHei UI", 10, "bold"), bg=BG_ALT)
        self._install_btn.pack(side="left")
        self._install_btn.set_enabled(False)
        self._close_btn = FlatButton(act, "关闭", command=self._on_close, kind="normal",
                                     height=36, width=84, bg=BG_ALT)
        self._close_btn.pack(side="right")

        prog = tk.Frame(right, bg=BG_ALT)
        prog.pack(fill="x", pady=(12, 0))
        ph = tk.Frame(prog, bg=BG_ALT, padx=16, pady=10)
        ph.pack(fill="x")
        self._progress = ProgressBar(ph, height=6)
        self._progress.pack(fill="x")
        self._prog_label = tk.Label(ph, text="", bg=BG_ALT, fg=FG_DIM, anchor="w",
                                    font=self.app.fonts["small"])
        self._prog_label.pack(fill="x", pady=(6, 0))

        log_card = tk.Frame(right, bg=BG_ALT)
        log_card.pack(fill="both", expand=True, pady=(12, 0))
        tk.Label(log_card, text="安装日志", bg=BG_ALT, fg=FG_DIM,
                 font=self.app.fonts["small"]).pack(anchor="w", padx=12, pady=(8, 4))
        tk.Frame(log_card, bg=BORDER, height=1).pack(fill="x")
        self._log = LogPanel(log_card, height=6)
        self._log.pack(fill="both", expand=True)

    # ------------------------------------------------------------ 版本列表

    def _set_tab(self, kind: str) -> None:
        self._kind = kind
        for k, btn in self._tab_buttons.items():
            btn.kind = "primary" if k == kind else "ghost"
            btn._draw()

    def _load(self, kind: str) -> None:
        if self._installing:
            self.app.notify("正在安装，请稍候", "warn")
            return
        self._set_tab(kind)
        self._versions = []
        self._selected = None
        self._rows.clear()
        for w in self._scroll.inner.winfo_children():
            w.destroy()
        self._big_name.configure(text="未选择版本")
        self._big_sub.configure(text="从左边选一个加载器版本")
        self._install_btn.set_enabled(False)
        self._list_hint.configure(text=f"正在获取 {loaders.KINDS[kind]} 版本列表…", fg=FG_DIM)
        self._prog_label.configure(text="")

        mc = self.mc_version

        def work():
            try:
                vers = loaders.list_versions(kind, mc)
                self.post(lambda: self._on_versions(kind, vers))
            except Exception as exc:                 # noqa: BLE001
                msg = f"{type(exc).__name__}: {exc}"
                self.post(lambda: self._on_versions_error(kind, msg))

        threading.Thread(target=work, daemon=True).start()

    def _on_versions(self, kind: str, vers: list) -> None:
        if kind != self._kind or not self.winfo_exists():
            return
        self._versions = vers
        self._list_hint.configure(
            text=f"{loaders.KINDS[kind]} 共 {len(vers)} 个版本" if vers
            else f"{self.mc_version} 没有可用的 {loaders.KINDS[kind]}",
            fg=FG_DIM)
        for v in vers[:200]:
            self._add_row(v)
        self._scroll.inner.update_idletasks()
        self.after_idle(self._scroll.scroll_to_top)
        if vers:
            self._select(vers[0])

    def _on_versions_error(self, kind: str, msg: str) -> None:
        if not self.winfo_exists():
            return
        self._list_hint.configure(text=f"获取失败：{msg[:60]}", fg=DANGER)
        self._log.write(f"获取 {loaders.KINDS[kind]} 版本失败：{msg}", "err")

    def _add_row(self, v: loaders.LoaderVersion) -> None:
        row = SelectableRow(self._scroll.inner, on_click=lambda ver=v: self._select(ver),
                            bg=BG_ALT, pad=8)
        row.pack(fill="x")
        color = SUCCESS if v.stable else FG_FAINT
        stripe = tk.Frame(row.inner, bg=color, width=3, height=26)
        stripe.pack(side="left", fill="y", padx=(0, 8))
        box = tk.Frame(row.inner, bg=BG_ALT)
        box.pack(side="left", fill="both", expand=True)
        tk.Label(box, text=v.version, bg=BG_ALT, fg=FG, anchor="w",
                 font=self.app.fonts["body"]).pack(fill="x")
        tk.Label(box, text="正式版" if v.stable else "测试版", bg=BG_ALT, fg=FG_FAINT,
                 anchor="w", font=self.app.fonts["small"]).pack(fill="x")
        row.attach()
        self._rows[v.version] = row

    def _select(self, v: loaders.LoaderVersion) -> None:
        self._selected = v
        for k, row in self._rows.items():
            row.set_selected(k == v.version)
        self._big_name.configure(text=v.version)
        full = loaders.full_version(self._kind, self.mc_version, v.version)
        target = (f"fabric-loader-{v.version}-{self.mc_version}"
                  if self._kind == "fabric" else full)
        self._big_sub.configure(
            text=f"{loaders.KINDS[self._kind]}   ·   装成版本 {target}\n"
                 f"独立版本，原版 {self.mc_version} 不受影响")
        self._install_btn.set_enabled(not self._installing)

    # ------------------------------------------------------------ 安装

    def _install(self) -> None:
        if self._installing or self._selected is None:
            return
        game_dir = self.app.cfg.game_dir
        javas = detect_all(game_dir, self.app.cfg.get("java_path") or "")
        java = pick_for_version(javas, 8)
        if java is None:
            messagebox.showerror("缺少 Java",
                                 "没有找到可用的 Java（安装器需要 Java 8 以上）\n"
                                 "请先在设置页指定 Java 路径。", parent=self)
            return

        self._installing = True
        self._cancel.clear()
        self._install_btn.set_enabled(False)
        self._close_btn.set_enabled(False)
        self._progress.set(0.05)
        self._prog_label.configure(text="准备安装…")
        self._log.write(f"—— 安装 {loaders.KINDS[self._kind]} {self._selected.version} ——")
        self._log.write(f"Java: {java.path}")
        kind, ver = self._kind, self._selected.version
        self._pulse = 0.05
        self._tick()

        def log(msg: str) -> None:
            self.post(lambda m=msg: self._log.write(m))

        def work():
            try:
                vid = loaders.install(kind, self.mc_version, ver, game_dir, str(java.path),
                                      log, self._cancel)
            except Exception as exc:                 # noqa: BLE001
                msg = f"{type(exc).__name__}: {exc}"
                self.post(lambda: self._done(False, msg, ""))
                return
            self.post(lambda: self._done(True, "", vid))

        threading.Thread(target=work, daemon=True).start()

    def _tick(self) -> None:
        if not self._installing or not self.winfo_exists():
            return
        self._pulse = min(0.92, self._pulse + 0.012)
        self._progress.set(self._pulse)
        self._prog_label.configure(text="正在安装，日志见下方…")
        try:
            self.after(220, self._tick)
        except tk.TclError:
            pass

    def _done(self, ok: bool, msg: str, vid: str) -> None:
        self._installing = False
        if not self.winfo_exists():
            return
        self._close_btn.set_enabled(True)
        self._install_btn.set_enabled(self._selected is not None)
        if ok:
            self._progress.set(1.0)
            self._prog_label.configure(text="安装完成")
            self._log.write(f"安装完成：{vid}", "ok")
            self.app.notify(f"{vid} 安装完成", "ok")
            if self._on_done is not None:
                try:
                    self._on_done(vid)
                except Exception:                    # noqa: BLE001
                    pass
        else:
            self._prog_label.configure(text="安装失败")
            self._log.write(f"安装失败：{msg}", "err")
            messagebox.showerror("安装失败", msg, parent=self)

    # ------------------------------------------------------------ 关闭

    def _on_close(self) -> None:
        if self._installing:
            if not messagebox.askyesno("正在安装",
                                       "安装还没结束，确定要关闭吗？\n"
                                       "已下载的文件会保留，下次可以接着装。", parent=self):
                return
            self._cancel.set()
        self.destroy()
