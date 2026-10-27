"""下载页：拉取版本清单、筛选、一键安装。"""

from __future__ import annotations

import re
import threading
import tkinter as tk
from tkinter import messagebox
from typing import Any

from ..downloader import Progress, fetch_json, human_size, human_speed
from ..installer import Installer
from ..versionmeta import VERSION_MANIFEST, VersionSummary, parse_manifest
from . import images, responsive
from .theme import (
    ACCENT, BG, BG_ALT, BG_HOVER, BORDER, DANGER, FG, FG_DIM, FG_FAINT,
    SUCCESS, WARN, FlatButton, ScrollFrame,
)
from .widgets import (
    LogPanel, Page, ProgressBar, Select, SelectableRow, TabBar,
)

#: 左栏（版本清单）的默认宽度，窗口变窄时由 _apply_width 收窄。
LEFT_W = 380
#: 左栏下限。再窄下去版本号那一行就放不下了。
LEFT_W_MIN = 240

FILTERS = [
    ("全部",   None),
    ("正式版", "release"),
    ("快照",   "snapshot"),
    ("远古版", "old"),
]

#: 下载页的页签：游戏版本（本页原内容）+ 四类 Modrinth 内容。
#: 用户反馈「不能下载模组 材质包啥的」——原先把这几类藏在 Mod 页的弹窗里，
#: 现在直接作为下载页的一等页签；整合包页签对应「整合包在线下载」。
DOWNLOAD_TABS = [
    ("version",      "游戏版本"),
    ("mod",          "模组"),
    ("resourcepack", "资源包"),
    ("shader",       "光影"),
    ("modpack",      "整合包"),
]

#: 一次渲染最多铺多少行版本。每行 6 个控件，超了就是给拉伸/滚动添负担：
#: 实测 400 行（2400 控件）时窗口拉伸到页面跟上要 1000 ms，60 行只要 ~330 ms。
ROW_BUDGET = 60

#: 版本列表里「大版本」分组用的哨兵值（下拉里显示成「全部版本」）。
ALL_FAMILY = "全部版本"

_FAMILY_RE = re.compile(r"^(\d+)\.(\d+)")
_SNAP_RE = re.compile(r"^\d{2}w\d{2}")
#: 预发布版（1.20-pre1 / 1.20-rc2）也要归到「快照」组，否则会被 1.20 组吃掉。
_PRE_RE = re.compile(r"^\d+\.\d+-(?:pre|rc)\d*$", re.IGNORECASE)


def version_family(v: VersionSummary) -> str:
    """把版本 id 归到一个「大版本」分组名里。

    用户反馈「列表可以按大版本号分类，现在几百行滚起来找不着」：1.21.4、
    1.21.1、1.21 归成 ``1.21``；快照（``24w14a``、``1.20-pre1``）单独一组；
    远古 alpha/beta 单独一组。
    """
    vid = (v.id or "").strip()
    if v.type in ("old_beta", "old_alpha"):
        return "远古版本"
    if _SNAP_RE.match(vid) or _PRE_RE.match(vid) or v.type == "snapshot":
        return "快照"
    m = _FAMILY_RE.match(vid)
    if m:
        return f"{m.group(1)}.{m.group(2)}"
    return "其他版本"


def _family_key(name: str) -> tuple:
    """分组排序：数字大版本倒序在前，特殊组垫底。"""
    m = re.match(r"^(\d+)\.(\d+)$", name)
    if m:
        return (0, -int(m.group(1)), -int(m.group(2)))
    order = {"快照": 1, "其他版本": 2, "远古版本": 3}
    return (4, order.get(name, 9), 0)



class InstallPage(Page):
    title = "下载"

    def build(self) -> None:
        self._all: list[VersionSummary] = []
        self._filter = "release"
        self._family = ALL_FAMILY
        self._rows: dict[str, SelectableRow] = {}
        self._selected: VersionSummary | None = None
        self._installing = False
        self._installer: Installer | None = None
        self._loading = False
        self._last_progress = None
        self._tick_job = None
        self._browser = None
        self._render_job = None
        self._render_sig = None
        # 每次最多渲染多少行。每行 6 个控件，400 行就是 2400 个，窗口一改宽
        # Tk 要把它们全部重排一遍——实测拉伸对齐从 320 ms 涨到 1000 ms。
        # 分组标题 + 下拉已经能把范围收窄，所以列表不必一次铺满。
        self._budget = ROW_BUDGET

        shell = tk.Frame(self, bg=BG)
        shell.pack(fill="both", expand=True)

        tabs_row = tk.Frame(shell, bg=BG)
        tabs_row.pack(fill="x", padx=24, pady=(10, 0))
        self._tabs = TabBar(tabs_row, DOWNLOAD_TABS, on_change=self._on_tab, bg=BG,
                            height=38, gap=28,
                            font=("Microsoft YaHei UI", 11),
                            font_active=("Microsoft YaHei UI", 11, "bold"))
        self._tabs.pack(side="left")

        self._stack = tk.Frame(shell, bg=BG)
        self._stack.pack(fill="both", expand=True)
        self._tab_version = tk.Frame(self._stack, bg=BG)
        self._tab_browser = tk.Frame(self._stack, bg=BG)
        self._tab_loader = tk.Frame(self._stack, bg=BG)   # 反馈⑫：加载器内嵌
        self._loader_panel = None

        root = tk.Frame(self._tab_version, bg=BG)
        root.pack(fill="both", expand=True, padx=24, pady=(8, 12))

        head = tk.Frame(root, bg=BG)
        head.pack(fill="x")
        tk.Label(head, text="选择要安装的版本", bg=BG, fg=FG,
                 font=self.app.fonts["h2"]).pack(side="left")
        self._count_label = tk.Label(head, text="", bg=BG, fg=FG_FAINT,
                                     font=self.app.fonts["small"])
        self._count_label.pack(side="right", pady=(4, 0))

        # ---------------- 工具条
        # 六个控件原来横排，窗口一窄右侧的「获取版本清单」就被挤出窗口外（用户
        # 反馈「往小调整窗口时按键要完整显示」）。改成 FlowRow：放不下自动换行。
        tools = responsive.FlowRow(root, gap=8, row_gap=8, bg=BG)
        tools.pack(fill="x", pady=(12, 10))
        self._tools = tools

        # 反馈⑩：版本号从一个纯输入框改成「大版本下拉 + 关键字」，
        # 下拉里直接列出 1.21.x / 1.20.x 这类大版本，点两下就能筛。
        self._fam_sel = Select(tools, values=[ALL_FAMILY], value=ALL_FAMILY,
                               on_change=self._on_family, width=14, height=30,
                               font=self.app.fonts["small"])

        self._search_var = tk.StringVar()
        search = tk.Entry(tools, textvariable=self._search_var, bg=BG_ALT, fg=FG,
                          insertbackground=FG, bd=0, highlightthickness=1,
                          highlightbackground=BORDER, highlightcolor=ACCENT,
                          font=self.app.fonts["body"], width=18)
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
            self._filter_buttons[label] = btn

        self._manifest_btn = FlatButton(tools, "获取版本清单",
                                        command=lambda: self.load_manifest(force=True),
                                        kind="normal", height=30, width=110,
                                        font=self.app.fonts["small"], bg=BG)

        tools.add_all(self._fam_sel, search, *self._filter_buttons.values(),
                      self._manifest_btn)

        # ---------------- 主体
        body = tk.Frame(root, bg=BG)
        body.pack(fill="both", expand=True)
        self._body = body

        left = tk.Frame(body, bg=BG_ALT, width=LEFT_W)
        left.pack(side="left", fill="both", expand=False)
        left.pack_propagate(False)
        self._left = left
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
        self._right = right

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
        self._act = responsive.FlowRow(act, gap=8, row_gap=8, bg=BG_ALT)
        self._act.pack(fill="x")
        self._install_btn = FlatButton(self._act, "下载并安装", command=self.start_install,
                                       kind="primary", height=38, width=140,
                                       font=("Microsoft YaHei UI", 10, "bold"), bg=BG_ALT)
        self._install_btn.set_enabled(False)
        self._cancel_btn = FlatButton(self._act, "取消", command=self.cancel_install,
                                      kind="danger", height=38, width=80, bg=BG_ALT)
        self._cancel_btn.set_enabled(False)
        self._loader_btn = FlatButton(self._act, "安装加载器…", command=self.open_loader_dialog,
                                      kind="normal", height=38, width=120, bg=BG_ALT)
        self._loader_btn.set_enabled(False)
        self._act.add_all(self._install_btn, self._cancel_btn, self._loader_btn)

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

        self._show_stack(self._tab_version)
        self.after(200, self.load_manifest)

    # ------------------------------------------------------------ 自适应宽度

    def _left_width(self) -> int:
        """左栏当前宽度（列表里的长文案按它换行；取不到就用设计宽度兜底）。"""
        left = getattr(self, "_left", None)
        if left is None:
            return LEFT_W
        try:
            return max(120, left.winfo_width())
        except tk.TclError:
            return LEFT_W

    def on_resize(self, width: int) -> None:
        """按页面宽度收窄左栏、重排工具条与按钮行。

        用户反馈「在往小调整窗口的时候自动调整分辨率使按键能够完整显示」：
        原来左栏固定 380、工具条六个控件横排，880x560 时右侧卡片被裁、
        「获取版本清单」只剩「获取」两个字。
        """
        if width <= 1:
            try:
                width = self.winfo_width()
            except tk.TclError:
                return
        if width <= 1:
            return
        w = width

        left_w = responsive.left_width(w, right_min=420, gap=18,
                                       lo=LEFT_W_MIN, hi=LEFT_W)
        try:
            self._left.configure(width=left_w)
        except (tk.TclError, AttributeError):
            return
        body_w = max(200, w - 48)
        right_w = max(200, w - 48 - left_w - 18)

        tools = getattr(self, "_tools", None)
        if tools is not None:
            try:
                tools.reflow(body_w)
            except tk.TclError:
                pass
        act = getattr(self, "_act", None)
        if act is not None:
            try:
                act.reflow(right_w - 36)
            except tk.TclError:
                pass

        # 版本号标题：Segoe UI 18 在窄右栏里会顶出去，降字号并允许换行
        size = 18 if right_w >= 380 else (16 if right_w >= 300 else 14)
        wrap = max(120, right_w - 36)
        try:
            self._big_name.configure(font=("Segoe UI", size, "bold"),
                                     wraplength=wrap)
            self._big_sub.configure(wraplength=wrap)
        except (tk.TclError, AttributeError):
            pass

    # ------------------------------------------------------------ 页签

    def _on_tab(self, key: str) -> None:
        if key == "version":
            self._show_stack(self._tab_version)
            return
        self._show_stack(self._tab_browser)
        browser = self._ensure_browser()
        mc, loader = self._mc_context()
        try:
            browser.set_context(game_version=mc, loader=loader)
            browser.set_type(key)
            browser.refresh()
        except Exception:                            # noqa: BLE001
            pass

    def _show_stack(self, frame: tk.Frame) -> None:
        """在版本列表 / Modrinth 浏览器 / 加载器面板之间切换（place 叠放）。"""
        for f in (self._tab_version, self._tab_browser, self._tab_loader):
            if f is frame:
                f.place(x=0, y=0, relwidth=1, relheight=1)
                f.lift()
            else:
                f.place_forget()

    def _mc_context(self) -> tuple[str, str]:
        """当前选中版本对应的真实 Minecraft 版本与加载器。

        不能直接把版本 id 当版本号用：``modpack``、``26.3`` 这类名字丢给
        Modrinth 的 ``versions:`` 过滤条件会是 0 个结果（用户反馈"不能下载
        模组"的直接原因之一）。这里回查版本 JSON 拿到真正的 MC 版本。
        """
        home = self.app._pages.get("home")
        vid = str(getattr(home, "_selected", "") or "")
        if not vid:
            return "", ""
        try:
            from pathlib import Path

            from .. import exportpack
            from ..launcher import GameLauncher

            game_dir = Path(str(self.app.cfg.game_dir))
            vjson = GameLauncher(game_dir).load_version(vid)
            mc, kind, _ver = exportpack.detect_dependencies(game_dir, vid, vjson)
            return (mc or "", kind or "")
        except Exception:                            # noqa: BLE001
            return ("", "")

    def _ensure_browser(self):
        if self._browser is not None:
            return self._browser
        from .download_browser import DownloadBrowser
        root = tk.Frame(self._tab_browser, bg=BG)
        root.pack(fill="both", expand=True, padx=24, pady=(8, 14))
        mc, loader = self._mc_context()
        self._browser = DownloadBrowser(
            root, self.app, project_type="mod", game_version=mc,
            loader=loader, target=None, show_type_tabs=False,
            on_log=lambda m: self._log.write(m))
        self._browser.pack(fill="both", expand=True)
        return self._browser

    def open_browser(self, project_type: str = "mod") -> None:
        """外部入口：切到下载页并打开指定类型的 Modrinth 浏览器。"""
        self._tabs.set(project_type, fire=True)

    # ------------------------------------------------------------ 清单

    def on_show(self) -> None:
        self.load_manifest()

    def on_version_selected(self, version_id: str) -> None:
        """首页换了选中版本 → 把下载页的 Mod 浏览器筛选条件同步过去。

        反馈⑮：以前下载页只在第一次构造浏览器时取一次上下文，用户换了版本
        再回来下载模组，版本/加载器还是旧的，搜出来一堆不兼容的东西。
        """
        if not version_id:
            return
        browser = self._browser
        if browser is None:
            return                              # 还没建，下次 _ensure_browser 会取最新值
        mc, loader = self._mc_context()
        try:
            browser.set_context(game_version=mc, loader=loader)
        except Exception:                            # noqa: BLE001
            pass

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
        self._sync_families()
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
        self._sync_families(keep=True)
        self._render_list()

    def _on_family(self, name: str) -> None:
        self._family = name
        self._render_list()

    def _on_search_typed(self) -> None:
        self._render_list()

    def _on_search_blur(self, _e=None) -> None:
        if not self._search_var.get().strip():
            try:
                self._ph.place(in_=self._search_entry, x=7, rely=0.5, anchor="w")
            except tk.TclError:
                pass

    def _ui_alive(self) -> bool:
        """界面是否还活着（换主题会把整棵树 destroy 重建）。"""
        try:
            return bool(self.winfo_exists()) and bool(self._scroll.inner.winfo_exists())
        except (tk.TclError, AttributeError):
            return False

    def _visible(self) -> list[VersionSummary]:
        """按「类型筛选 + 大版本 + 关键字」过滤后的版本列表。"""
        query = self._search_var.get().strip().lower()
        out = []
        for v in self._all:
            if self._filter == "old":
                if v.type not in ("old_beta", "old_alpha"):
                    continue
            elif self._filter and v.type != self._filter:
                continue
            if self._family != ALL_FAMILY and version_family(v) != self._family:
                continue
            if query and query not in v.id.lower():
                continue
            out.append(v)
        return out

    def _families(self) -> list[str]:
        """当前类型筛选下出现过的所有大版本分组（用于下拉）。"""
        def ok(v: VersionSummary) -> bool:
            if self._filter == "old":
                return v.type in ("old_beta", "old_alpha")
            if self._filter:
                return v.type == self._filter
            return True

        names = {version_family(v) for v in self._all if ok(v)}
        return [ALL_FAMILY] + sorted(names, key=_family_key)

    def _sync_families(self, keep: bool = False) -> None:
        names = self._families()
        if keep and self._family in names:
            pass
        elif self._family not in names:
            self._family = ALL_FAMILY
        try:
            self._fam_sel.set_values(names)
            self._fam_sel.set(self._family)
        except (tk.TclError, AttributeError):
            pass

    def _render_list(self) -> None:
        # 反馈⑪：切换筛选/下拉时原先是同步全量销毁重建，几百个版本要几百毫秒。
        # 现在合并成一次 after(1) 的空闲渲染，连续切换只会画最后一帧。
        if self._render_job is not None:
            try:
                self.after_cancel(self._render_job)
            except (tk.TclError, ValueError):
                pass
            self._render_job = None
        self._render_job = self.after(1, self._render_now)

    def _render_now(self) -> None:
        self._render_job = None
        # 换主题会销毁整棵界面重建，但排队的 after(1) 还会跑到这里；
        # 此时 _scroll.inner 已经在 Tcl 侧被销毁，winfo_children() 会抛
        # TclError（bad window path name），必须先确认控件还活着。
        if not self._ui_alive():
            return
        shown = self._visible()
        sig = (id(self._all), len(self._all), self._filter, self._family,
               self._search_var.get().strip().lower(), len(shown),
               getattr(self, "_budget", ROW_BUDGET))
        if sig == self._render_sig and self._rows:
            return
        self._render_sig = sig

        for w in self._scroll.inner.winfo_children():
            w.destroy()
        self._rows.clear()
        self._empty_hint = None

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

        # 反馈⑪：按大版本分组，每组前加一条分组标题。
        groups: dict[str, list[VersionSummary]] = {}
        for v in shown:
            groups.setdefault(version_family(v), []).append(v)
        limit = getattr(self, "_budget", ROW_BUDGET) or ROW_BUDGET
        budget = limit
        for name in sorted(groups, key=_family_key):
            if budget <= 0:
                # wraplength 必须给：这行是「……还有 N 个版本没有列出，用上方
                # 下拉或搜索缩小范围」，左栏窄到 240 时它要 284px，不换行就被
                # 右侧的滚动条压掉一截（880x560 实测被压 76px）。
                tk.Label(self._scroll.inner,
                         text=f"……还有 {len(shown) - (limit - budget)} 个版本没有列出，"
                              f"用上方下拉或搜索缩小范围",
                         bg=BG_ALT, fg=FG_FAINT, font=self.app.fonts["small"],
                         justify="left",
                         wraplength=max(120, self._left_width() - 40)).pack(
                             fill="x", pady=(10, 4), padx=9, anchor="w")
                break
            items = groups[name]
            self._add_group_head(name, len(items))
            for v in items:
                if budget <= 0:
                    break
                self._add_row(v)
                budget -= 1

        self._scroll.scroll_to_top()
        # 选中项若还在列表里，保持高亮。
        if self._selected is not None:
            row = self._rows.get(self._selected.id)
            if row is not None:
                row.set_selected(True)

    def _add_group_head(self, name: str, count: int) -> None:
        head = tk.Frame(self._scroll.inner, bg=BG_ALT)
        head.pack(fill="x", pady=(10, 2), padx=9)
        tk.Label(head, text=name, bg=BG_ALT, fg=FG_DIM,
                 font=("Microsoft YaHei UI", 9, "bold")).pack(side="left")
        tk.Label(head, text=f"  {count} 个", bg=BG_ALT, fg=FG_FAINT,
                 font=self.app.fonts["small"]).pack(side="left")

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
        """反馈⑫：把原来的 LoaderDialog 弹窗换成内嵌面板。"""
        if self._installing or not self._selected:
            return
        from .loader_panel import LoaderPanel

        mc = self._selected.id
        for w in self._tab_loader.winfo_children():
            w.destroy()
        self._loader_panel = LoaderPanel(self._tab_loader, self.app, mc,
                                         on_done=self._on_loader_done,
                                         on_back=self._close_loader_panel)
        self._loader_panel.pack(fill="both", expand=True)
        self._show_stack(self._tab_loader)
        self.app.notify(f"选择要安装到 {mc} 的加载器", "info")

    def _close_loader_panel(self) -> None:
        panel, self._loader_panel = self._loader_panel, None
        if panel is not None:
            try:
                panel.destroy()
            except tk.TclError:
                pass
        self._show_stack(self._tab_version)

    def _on_loader_done(self, vid: str) -> None:
        home = self.app._pages.get("home")
        if home is not None:
            home.reload_versions()
        self._close_loader_panel()

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
