"""Modrinth 模组搜索 / 下载对话框。"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path

from .. import modrinth
from ..downloader import Progress, human_size
from ..mods import mods_dir, open_folder
from .theme import (
    ACCENT, BG, BG_ALT, BG_HOVER, BORDER, DANGER, FG, FG_DIM, FG_FAINT,
    SUCCESS, WARN, FlatButton, ScrollFrame,
)
from .widgets import ProgressBar, SelectableRow

_LOADER_CYCLE = ["", "fabric", "forge", "neoforge", "quilt"]
_LOADER_TEXT = {"": "全部加载器", "fabric": "Fabric", "forge": "Forge",
                "neoforge": "NeoForge", "quilt": "Quilt"}


class ModDownloadDialog(tk.Toplevel):
    """暗色搜索面板：左边结果，右边该模组的版本文件。"""

    def __init__(self, master, app, game_version: str = "", loader: str = "",
                 target=None):
        super().__init__(master, bg=BG)
        self.app = app
        self._target = target            # 下载到哪个目录（实例隔离时是实例目录）
        self._projects: list[modrinth.ModProject] = []
        self._versions: list[modrinth.ModVersion] = []
        self._project: modrinth.ModProject | None = None
        self._version: modrinth.ModVersion | None = None
        self._rows: dict[str, SelectableRow] = {}
        self._vrows: dict[str, SelectableRow] = {}
        self._busy = False

        self.title("下载 Mod — Modrinth")
        self.configure(bg=BG)
        w, h = 880, 580
        self.geometry(f"{w}x{h}")
        self.minsize(760, 480)
        self.transient(master)
        self._center(master, w, h)

        self._game_version = game_version
        self._loader = loader if loader in modrinth.LOADERS else ""
        self._ptype = "mod"
        self._type_btns: dict[str, FlatButton] = {}

        self._build()
        self.bind("<Escape>", lambda _e: self.destroy())
        self.after(120, lambda: self._entry.focus_set())

    # ------------------------------------------------------------ 布局

    def _center(self, master, w: int, h: int) -> None:
        try:
            master.update_idletasks()
            mx, my = master.winfo_rootx(), master.winfo_rooty()
            mw, mh = master.winfo_width(), master.winfo_height()
            self.geometry(f"{w}x{h}+{mx + (mw - w) // 2}+{my + max(0, (mh - h) // 2)}")
        except tk.TclError:
            pass

    def _build(self) -> None:
        root = tk.Frame(self, bg=BG)
        root.pack(fill="both", expand=True, padx=18, pady=14)

        head = tk.Frame(root, bg=BG)
        head.pack(fill="x")
        tk.Label(head, text="下载游戏内容", bg=BG, fg=FG,
                 font=self.app.fonts["h2"]).pack(side="left")
        tk.Label(head, text="数据来自 Modrinth", bg=BG, fg=FG_FAINT,
                 font=self.app.fonts["small"]).pack(side="left", padx=(10, 0), pady=(4, 0))
        FlatButton(head, "打开目录", command=self._open_mods, kind="ghost",
                   height=28, width=120, font=self.app.fonts["small"],
                   bg=BG).pack(side="right")

        # ---- 内容类型
        kinds = tk.Frame(root, bg=BG)
        kinds.pack(fill="x", pady=(10, 0))
        for key in ("mod", "resourcepack", "shader"):
            label = modrinth.CONTENT_TYPES[key][1]
            btn = FlatButton(kinds, label, command=lambda k=key: self._set_type(k),
                             kind="primary" if key == self._ptype else "ghost",
                             height=26, width=72, font=self.app.fonts["small"], bg=BG)
            btn.pack(side="left", padx=(0, 6))
            self._type_btns[key] = btn
        self._kind_hint = tk.Label(
            kinds, text="装进 mods 目录，需要对应的加载器", bg=BG, fg=FG_FAINT,
            font=self.app.fonts["small"])
        self._kind_hint.pack(side="left", padx=(8, 0))

        # ---- 搜索条件
        bar = tk.Frame(root, bg=BG)
        bar.pack(fill="x", pady=(10, 10))

        self._entry_var = tk.StringVar()
        self._entry = tk.Entry(bar, textvariable=self._entry_var, bg=BG_ALT, fg=FG,
                               insertbackground=FG, bd=0, highlightthickness=1,
                               highlightbackground=BORDER, highlightcolor=ACCENT,
                               font=self.app.fonts["body"], width=28)
        self._entry.pack(side="left", ipady=5)
        self._entry.bind("<Return>", lambda _e: self.do_search())
        self._ph = tk.Label(bar, text="中英文都行，例如 小地图 / 优化 / sodium", bg=BG_ALT,
                            fg=FG_FAINT, bd=0, font=self.app.fonts["small"])
        self._ph.place(in_=self._entry, x=7, rely=0.5, anchor="w")
        self._entry.bind("<FocusIn>", lambda _e: self._ph.place_forget())
        self._entry.bind("<FocusOut>", lambda _e: self._ph.place(in_=self._entry, x=7, rely=0.5, anchor="w")
                         if not self._entry_var.get().strip() else None)

        self._ver_var = tk.StringVar(value=self._game_version or "")
        ver = tk.Entry(bar, textvariable=self._ver_var, bg=BG_ALT, fg=FG,
                       insertbackground=FG, bd=0, highlightthickness=1,
                       highlightbackground=BORDER, highlightcolor=ACCENT,
                       font=self.app.fonts["body"], width=11)
        ver.pack(side="left", padx=(8, 0), ipady=5)

        self._loader_btn = FlatButton(
            bar, _LOADER_TEXT[self._loader], command=self._cycle_loader,
            kind="normal", height=30, width=96, font=self.app.fonts["small"], bg=BG)
        self._loader_btn.pack(side="left", padx=(8, 0))

        FlatButton(bar, "搜索", command=self.do_search, kind="primary", height=30,
                   width=70, font=self.app.fonts["small"], bg=BG).pack(side="left", padx=(8, 0))

        # ---- 两栏
        body = tk.Frame(root, bg=BG)
        body.pack(fill="both", expand=True)

        left = tk.Frame(body, bg=BG_ALT)
        left.pack(side="left", fill="both", expand=True)
        self._lhead = tk.Label(left, text="搜索结果", bg=BG_ALT, fg=FG_DIM,
                               font=self.app.fonts["small"], anchor="w", padx=10, pady=7)
        self._lhead.pack(fill="x")
        tk.Frame(left, bg=BORDER, height=1).pack(fill="x")
        self._lscroll = ScrollFrame(left, bg=BG_ALT)
        self._lscroll.pack(fill="both", expand=True)

        tk.Frame(body, bg=BG, width=10).pack(side="left")

        right = tk.Frame(body, bg=BG_ALT, width=330)
        right.pack(side="right", fill="both")
        right.pack_propagate(False)
        self._rhead = tk.Label(right, text="版本文件", bg=BG_ALT, fg=FG_DIM,
                               font=self.app.fonts["small"], anchor="w", padx=10, pady=7)
        self._rhead.pack(fill="x")
        tk.Frame(right, bg=BORDER, height=1).pack(fill="x")
        self._rscroll = ScrollFrame(right, bg=BG_ALT)
        self._rscroll.pack(fill="both", expand=True)

        # ---- 底部
        foot = tk.Frame(root, bg=BG)
        foot.pack(fill="x", pady=(10, 0))
        self._status = tk.Label(foot, text="输入关键字开始搜索", bg=BG, fg=FG_FAINT,
                                font=self.app.fonts["small"], anchor="w")
        self._status.pack(side="left", fill="x", expand=True)
        self._dl_btn = FlatButton(foot, "下载并安装", command=self.download_selected,
                                  kind="primary", height=34, width=120,
                                  font=self.app.fonts["body"], bg=BG)
        self._dl_btn.pack(side="right")
        self._dl_btn.set_enabled(False)

        self._progress = ProgressBar(foot, height=4)
        self._progress.pack(side="right", fill="x", expand=True, padx=(16, 16))
        self._progress.pack_forget()

    # ------------------------------------------------------------ 工具

    def _set_status(self, text: str, kind: str = "info") -> None:
        color = {"ok": SUCCESS, "warn": WARN, "err": DANGER}.get(kind, FG_FAINT)
        try:
            self._status.configure(text=text, fg=color)
        except tk.TclError:
            pass

    def _set_type(self, key: str) -> None:
        """切换内容类型（模组 / 资源包 / 光影），同时更新提示语和按钮样式。"""
        if key == self._ptype:
            return
        self._ptype = key
        for k, btn in self._type_btns.items():
            btn.kind = "primary" if k == key else "ghost"
            btn._draw()
        hints = {
            "mod": "装进 mods 目录，需要对应的加载器",
            "resourcepack": "装进 resourcepacks 目录，在游戏里「资源包」中启用",
            "shader": "装进 shaderpacks 目录，需要 Iris / OptiFine 才能加载",
        }
        self._kind_hint.configure(text=hints.get(key, ""))
        name = modrinth.CONTENT_TYPES.get(key, ("mods", "内容"))[1]
        self._entry_ph = {
            "mod": "中文/英文都行，例如 小地图、优化、sodium",
            "resourcepack": "例如 材质包、faithful、xali",
            "shader": "例如 光影、complementary、bsl",
        }.get(key, f"搜索{name}")
        self._ph.configure(text=self._entry_ph)
        if key != "mod":
            self._loader_btn.pack_forget()
        else:
            if not self._loader_btn.winfo_ismapped():
                self._loader_btn.pack(side="left", padx=(8, 0))
        self._clear(self._lscroll)
        self._clear(self._rscroll)
        self._rows.clear()
        self._vrows.clear()
        self._project = None
        self._version = None
        self._dl_btn.set_enabled(False)
        self._lhead.configure(text=f"{name}搜索结果")
        if self._entry_var.get().strip():
            self.do_search()
        else:
            self._set_status(f"输入关键字搜索{name}")

    def _open_folder(self) -> None:
        open_folder(modrinth.target_dir(self._target or self.app.cfg.game_dir, self._ptype))

    def _cycle_loader(self) -> None:
        i = _LOADER_CYCLE.index(self._loader) if self._loader in _LOADER_CYCLE else 0
        self._loader = _LOADER_CYCLE[(i + 1) % len(_LOADER_CYCLE)]
        self._loader_btn.set_text(_LOADER_TEXT[self._loader])

    def _clear(self, scroll: ScrollFrame) -> None:
        for w in scroll.inner.winfo_children():
            w.destroy()

    # ------------------------------------------------------------ 搜索

    def do_search(self) -> None:
        if self._busy:
            return
        query = self._entry_var.get().strip()
        if not query:
            self._set_status("请输入模组名", "warn")
            return
        from .. import cnsearch
        english, hint = cnsearch.translate(query)
        if not english:
            self._set_status(f"没认出「{query}」里的中文关键词，换个说法试试"
                             f"（比如「小地图」「优化」「钠」）", "warn")
            return
        self._busy = True
        self._clear(self._lscroll)
        self._clear(self._rscroll)
        self._rows.clear()
        self._vrows.clear()
        self._project = None
        self._version = None
        self._dl_btn.set_enabled(False)
        self._lhead.configure(text=f"搜索 “{query}” 中…")
        self._set_status(f"中文关键词：{hint} → 按 “{english}” 搜索" if hint
                         else "正在请求 Modrinth…")

        gv = self._ver_var.get().strip()
        loader = self._loader if self._ptype == "mod" else ""

        def work():
            try:
                hits, total = modrinth.search(english, gv, loader, limit=25,
                                              project_type=self._ptype)
            except Exception as exc:                  # noqa: BLE001
                self.app.post(lambda: self._search_done(None, 0, str(exc)))
                return
            self.app.post(lambda: self._search_done(
                hits, total, "", f"{query} → {english}" if hint else ""))

        threading.Thread(target=work, daemon=True).start()

    def _search_done(self, hits, total: int, error: str, renamed: str = "") -> None:
        self._busy = False
        if error or hits is None:
            self._lhead.configure(text="搜索失败")
            self._set_status(f"搜索失败：{error}", "err")
            return
        self._projects = list(hits)
        suffix = f"（{renamed}）" if renamed else ""
        self._lhead.configure(text=f"搜索结果{suffix}（{total} 个，显示 {len(hits)} 个）")
        self._set_status(f"共 {total} 个结果，点左边选一个查看版本")
        if not hits:
            box = tk.Frame(self._lscroll.inner, bg=BG_ALT)
            box.pack(fill="x", pady=40)
            tk.Label(box, text="没有找到匹配的模组", bg=BG_ALT, fg=FG_DIM,
                     font=self.app.fonts["body"]).pack()
            return
        for p in hits:
            self._add_project_row(p)

    def _add_project_row(self, p: modrinth.ModProject) -> None:
        row = SelectableRow(self._lscroll.inner, on_click=lambda: self._pick(p),
                            bg=BG_ALT, pad=8)
        row.pack(fill="x")

        # 先 pack 右侧的元信息，否则左边 expand 的文本会把它挤到边界外
        meta = tk.Frame(row.inner, bg=BG_ALT)
        meta.pack(side="right")
        tk.Label(meta, text=p.loader_label or "—", bg=BG_ALT, fg=FG_DIM,
                 anchor="e", font=self.app.fonts["small"]).pack(side="top")
        tk.Label(meta, text=f"↓ {p.downloads_label}", bg=BG_ALT, fg=FG_FAINT,
                 anchor="e", font=self.app.fonts["small"]).pack(side="top")

        box = tk.Frame(row.inner, bg=BG_ALT)
        box.pack(side="left", fill="both", expand=True)
        tk.Label(box, text=p.title, bg=BG_ALT, fg=FG, anchor="w",
                 font=self.app.fonts["body"]).pack(fill="x")
        desc = p.description or ""
        if len(desc) > 44:
            desc = desc[:44] + "…"
        tk.Label(box, text=desc, bg=BG_ALT, fg=FG_FAINT, anchor="w",
                 font=self.app.fonts["small"]).pack(fill="x")

        row.attach()
        self._rows[p.project_id] = row

    def _pick(self, p: modrinth.ModProject) -> None:
        self._project = p
        for k, row in self._rows.items():
            row.set_selected(k == p.project_id)
        self._rhead.configure(text=f"{p.title} 的版本")
        self._set_status("正在获取版本列表…")
        self._clear(self._rscroll)
        self._vrows.clear()
        self._version = None
        self._dl_btn.set_enabled(False)

        gv = self._ver_var.get().strip()
        loader = self._loader if self._ptype == "mod" else ""

        def work():
            try:
                vs = modrinth.versions(p.project_id, gv, loader)
            except Exception as exc:                  # noqa: BLE001
                self.app.post(lambda: self._versions_done([],
                                                          f"{type(exc).__name__}: {exc}"))
                return
            self.app.post(lambda: self._versions_done(vs, ""))

        threading.Thread(target=work, daemon=True).start()

    def _versions_done(self, vs, error: str) -> None:
        self._versions = list(vs)
        if error:
            self._set_status(f"获取版本失败：{error}", "err")
            return
        if not vs:
            box = tk.Frame(self._rscroll.inner, bg=BG_ALT)
            box.pack(fill="x", pady=30)
            tk.Label(box, text="这个筛选条件下没有可用版本", bg=BG_ALT, fg=FG_DIM,
                     justify="left", font=self.app.fonts["small"]).pack()
            tk.Label(box, text="试试清空游戏版本或换成「全部加载器」", bg=BG_ALT,
                     fg=FG_FAINT, font=self.app.fonts["small"]).pack()
            self._set_status("没有可用版本", "warn")
            return
        self._set_status(f"共 {len(vs)} 个版本，选一个下载")
        for v in vs:
            self._add_version_row(v)

    def _add_version_row(self, v: modrinth.ModVersion) -> None:
        row = SelectableRow(self._rscroll.inner, on_click=lambda: self._pick_version(v),
                            bg=BG_ALT, pad=7)
        row.pack(fill="x")

        box = tk.Frame(row.inner, bg=BG_ALT)
        box.pack(side="left", fill="both", expand=True)
        tk.Label(box, text=v.version_number or v.name, bg=BG_ALT, fg=FG, anchor="w",
                 font=self.app.fonts["small"]).pack(fill="x")
        gvs = ", ".join(v.game_versions[:3]) or "—"
        sub = f"{gvs}    {v.date}"
        tk.Label(box, text=sub, bg=BG_ALT, fg=FG_FAINT, anchor="w",
                 font=("Microsoft YaHei UI", 8)).pack(fill="x")

        f = modrinth.primary_file(v)
        color = {"release": SUCCESS, "beta": WARN, "alpha": DANGER}.get(
            f.release_type if f else "release", FG_FAINT)
        tk.Label(row.inner, text=f.size_label if f else "?", bg=BG_ALT, fg=color,
                 width=9, anchor="e", font=("Microsoft YaHei UI", 8)).pack(side="right")

        self._vrows[v.version_id] = row

    def _pick_version(self, v: modrinth.ModVersion) -> None:
        self._version = v
        for k, row in self._vrows.items():
            row.set_selected(k == v.version_id)
        f = modrinth.primary_file(v)
        if f:
            self._set_status(f"已选择 {v.version_number} → {f.filename}（{f.size_label}）")
        self._dl_btn.set_enabled(bool(f))

    # ------------------------------------------------------------ 下载

    def download_selected(self) -> None:
        if not self._version:
            return
        f = modrinth.primary_file(self._version)
        if not f:
            self._set_status("这个版本没有可下载的文件", "err")
            return
        base = self._target or self.app.cfg.game_dir
        target = modrinth.target_dir(base, self._ptype)

        self._dl_btn.set_enabled(False)
        self._progress.pack(side="right", fill="x", expand=True, padx=(16, 16))
        self._progress.set(0.0)
        self._set_status(f"正在下载 {f.filename} …")

        last = [0.0]
        stop = threading.Event()

        def tick(progress: Progress):
            import time
            now = time.time()
            if now - last[0] < 0.1:
                return
            last[0] = now
            pct, cur, speed = progress.snapshot()
            self.app.post(lambda: self._progress.set(pct))

        def work():
            ok, bad = modrinth.download(
                [f], target,
                progress_cb=lambda p: tick(p),
                on_log=lambda m: None,
            )
            def done():
                stop.set()
                self._progress.pack_forget()
                self._dl_btn.set_enabled(True)
                if ok and not bad:
                    folder = modrinth.CONTENT_TYPES.get(self._ptype, ("mods", ""))[0]
                    self._set_status(f"已安装到 {folder}：{f.filename}", "ok")
                    self.app.notify(f"已下载 {f.filename}", "ok")
                else:
                    self._set_status(f"下载失败（{bad} 个文件）", "err")
            self.app.post(done)

        threading.Thread(target=work, daemon=True).start()
