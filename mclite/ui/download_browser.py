"""Modrinth 内容浏览器（内嵌版）：左边搜索结果，右边该项目的版本文件。

这是原来 ``mod_dialog.ModDownloadDialog`` 那个模态窗口的 Frame 版本：
- 不再自己创建 Toplevel、不 grab_set、不 wait_window、不 transient，
  也没有标题栏 / 关闭按钮 —— 窗口层面的装饰由宿主页面提供；
- 所有网络与下载都在后台线程，UI 更新一律经 ``self.app.post`` 回到主线程；
- 中文搜索沿用 ``cnsearch.translate``，不在这里另做一套词表。

宿主通常这样用::

    browser = DownloadBrowser(page, self.app, project_type="mod",
                              game_version="1.20.1", loader="fabric",
                              target=instance_dir, on_log=self.log.write)
    browser.pack(fill="both", expand=True)
"""

from __future__ import annotations

import threading
import time
import tkinter as tk
from pathlib import Path

from .. import modrinth
from ..downloader import Progress
from ..mods import open_folder
from .theme import (
    ACCENT, BG, BG_ALT, BORDER, DANGER, FG, FG_DIM, FG_FAINT,
    SUCCESS, WARN, FlatButton, ScrollFrame,
)
from .widgets import ProgressBar, Select, SelectableRow

ALL_VERSIONS = "全部版本"

_LOADER_CYCLE = ["", "fabric", "forge", "neoforge", "quilt"]
_LOADER_TEXT = {"": "全部加载器", "fabric": "Fabric", "forge": "Forge",
                "neoforge": "NeoForge", "quilt": "Quilt"}

#: 标签页顺序：模组 / 资源包 / 光影 / 整合包
_TAB_ORDER = ("mod", "resourcepack", "shader", "modpack")

#: 每种内容类型的存放说明
_TYPE_HINT = {
    "mod": "装进 mods 目录，需要对应的加载器",
    "resourcepack": "装进 resourcepacks 目录，在游戏里「资源包」中启用",
    "shader": "装进 shaderpacks 目录，需要 Iris / OptiFine 才能加载",
    "modpack": "整合包，包含自己的版本与配置文件",
}

#: 每种内容类型的搜索框占位提示
_TYPE_PLACEHOLDER = {
    "mod": "中文/英文都行，例如 小地图、优化、sodium",
    "resourcepack": "例如 材质包、faithful、xali",
    "shader": "例如 光影、complementary、bsl",
    "modpack": "例如 优化、冒险、fabulously、adrenas",
}


class DownloadBrowser(tk.Frame):
    """内嵌的内容浏览器：搜索 → 选项目 → 选版本 → 下载并安装。

    和原来的对话框相比，本类只负责「搜索 / 选择 / 下载」这三件事，
    其余（页签、标题、关闭）交给宿主页面，因此可以被放在任意容器里。
    """

    def __init__(self, master, app, project_type: str = "mod",
                 game_version: str = "", loader: str = "",
                 target=None, show_type_tabs: bool = True,
                 on_log=None):
        """构造内嵌浏览器：不创建窗口、不抢焦点、不阻塞调用方。"""
        super().__init__(master, **self._frame_kwargs(master))
        self.app = app
        self._on_log = on_log
        self._target = Path(target) if target is not None else None
        self._show_type_tabs = bool(show_type_tabs)

        self._game_version = (game_version or "").strip()
        self._loader = loader if loader in modrinth.LOADERS else ""
        self._ptype = project_type if project_type in modrinth.CONTENT_TYPES else "mod"

        # ---- 数据状态
        self._projects: list[modrinth.ModProject] = []
        self._versions: list[modrinth.ModVersion] = []
        self._project: modrinth.ModProject | None = None
        self._version: modrinth.ModVersion | None = None
        self._rows: dict[str, SelectableRow] = {}
        self._vrows: dict[str, SelectableRow] = {}
        self._busy = False
        # 代次号：每次清空列表就 +1。异步回调只认自己那一代的结果，
        # 否则切页签 / 重搜后，上一个请求晚到的结果会覆盖当前界面。
        self._gen = 0

        # ---- 控件状态
        self._type_btns: dict[str, FlatButton] = {}
        self._loader_visible = False
        self._entry_ph = ""

        self._build()
        self._sync_type_ui()

    @staticmethod
    def _frame_kwargs(master) -> dict:
        """宿主已经给过底色时沿用，避免出现一条不同颜色的缝。"""
        try:
            bg = master["bg"] if "bg" in master.keys() else BG
        except tk.TclError:
            bg = BG
        return {"bg": bg}

    # ------------------------------------------------------------ 布局

    def _build(self) -> None:
        root = tk.Frame(self, bg=BG)
        root.pack(fill="both", expand=True)

        # ---- 内容类型（show_type_tabs=False 时整行只留提示与「打开目录」）
        kinds = tk.Frame(root, bg=BG)
        kinds.pack(fill="x")
        if self._show_type_tabs:
            for key in _TAB_ORDER:
                label = modrinth.CONTENT_TYPES[key][1]
                btn = FlatButton(kinds, label, command=lambda k=key: self.set_type(k),
                                 kind="primary" if key == self._ptype else "ghost",
                                 height=26, width=72, font=self.app.fonts["small"], bg=BG)
                btn.pack(side="left", padx=(0, 6))
                self._type_btns[key] = btn
        self._kind_hint = tk.Label(kinds, text="", bg=BG, fg=FG_FAINT,
                                   font=self.app.fonts["small"])
        self._kind_hint.pack(side="left", padx=(8 if self._show_type_tabs else 0, 0))

        FlatButton(kinds, "打开目录", command=self._open_folder, kind="ghost",
                   height=26, width=92, font=self.app.fonts["small"],
                   bg=BG).pack(side="right")

        # ---- 搜索条件
        bar = tk.Frame(root, bg=BG)
        bar.pack(fill="x", pady=(10, 10))

        self._entry_var = tk.StringVar()
        self._entry = tk.Entry(bar, textvariable=self._entry_var, bg=BG_ALT, fg=FG,
                               insertbackground=FG, bd=0, highlightthickness=1,
                               highlightbackground=BORDER, highlightcolor=ACCENT,
                               font=self.app.fonts["body"], width=28)
        # 输入框吃掉剩余宽度：占位文字很长，宽度不够会被截断成半截字
        self._entry.pack(side="left", fill="x", expand=True, ipady=5)
        self._entry.bind("<Return>", lambda _e: self.do_search())

        # 占位文字用 place 叠在输入框上：输入框为空时显示，聚焦时让开。
        # 注意标签必须是 entry 的子控件（不能是 bar 的）——place(in_=...) 只借坐标
        # 不做裁剪，挂在 bar 上时超长的中文占位会溢出输入框、压住右边的「版本」框。
        # 挂在 entry 里面，Tk 会按父窗口边界裁剪，多出来的字自然被切掉。
        self._ph = tk.Label(self._entry, text="", bg=BG_ALT, fg=FG_FAINT, bd=0,
                            font=self.app.fonts["small"], anchor="w", padx=7,
                            takefocus=0)
        # 标签盖满整个输入框，鼠标点上去其实是点在标签上，得手动把焦点转给输入框
        self._ph.bind("<Button-1>", self._on_placeholder_click)
        self._place_placeholder()
        # 空着的时候把光标藏起来，否则光标会和占位文字叠成「/中文/英文…」
        self._entry.configure(insertwidth=0)
        self._entry.bind("<FocusIn>", self._on_entry_focus)
        self._entry.bind("<FocusOut>", self._on_entry_blur)
        self._entry_var.trace_add("write", lambda *_a: self._on_entry_text())

        tk.Label(bar, text="版本", bg=BG, fg=FG_DIM,
                 font=self.app.fonts["small"]).pack(side="left", padx=(10, 4))
        # 反馈⑩：版本框原来是个自由输入框，用户得手打 1.20.1 才知道能填什么，
        # 而且打错就是 0 结果。改成下拉：默认「全部版本」+ 本机已装版本 + 上游清单。
        self._ver_var = tk.StringVar(value=self._game_version or "")
        self._ver_sel = Select(bar, values=self._version_values(),
                               value=self._game_version or ALL_VERSIONS,
                               on_change=self._on_version_pick, width=11,
                               height=30, font=self.app.fonts["small"])
        self._ver_sel.pack(side="left")
        self._ver_sel.configure(width=118)

        self._loader_btn = FlatButton(
            bar, _LOADER_TEXT[self._loader], command=self._cycle_loader,
            kind="normal", height=30, width=96, font=self.app.fonts["small"], bg=BG)

        self._search_btn = FlatButton(bar, "搜索", command=self.do_search,
                                      kind="primary", height=30, width=70,
                                      font=self.app.fonts["small"], bg=BG)
        self._search_btn.pack(side="left", padx=(8, 0))

        # ---- 两栏：左结果 / 右版本
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
        self._dl_btn = FlatButton(foot, "下载所选", command=self.download_selected,
                                  kind="primary", height=34, width=120,
                                  font=self.app.fonts["body"], bg=BG)
        self._dl_btn.pack(side="right")
        self._dl_btn.set_enabled(False)
        self._progress = ProgressBar(foot, height=4)
        self._progress.pack(side="right", fill="x", expand=True, padx=(16, 16))
        self._progress.pack_forget()

    def _place_placeholder(self) -> None:
        """把占位标签铺满输入框内区（挂在 entry 里，超出部分由 Tk 裁剪）。

        内缩 2px 并各自减 4px，是为了不盖住 Entry 那圈 1px 描边——否则聚焦时的
        高亮边框会被这块背景色吃掉，输入框看起来像没有边。
        """
        try:
            self._ph.place(x=2, y=2, relwidth=1.0, relheight=1.0,
                           width=-4, height=-4)
        except tk.TclError:
            pass

    def _placeholder_visible(self) -> None:
        """占位文字只在「输入框为空」且「没有焦点」时显示。

        以前只在 FocusOut 时补回来、FocusIn 时藏起来，但只要文字是被代码写进去的
        （例如脚本里 `_entry_var.set("小地图")` 或切类型后回填），就不会触发 FocusIn，
        占位标签会一直盖在真实文字上面 —— 用户看到的就是左边露半个字。
        """
        empty = not self._entry_var.get().strip()
        try:
            focused = self._entry.focus_get() is self._entry
        except (tk.TclError, KeyError):
            focused = False
        if empty and not focused:
            self._place_placeholder()
        else:
            self._ph.place_forget()

    def _on_entry_focus(self, _event=None) -> None:
        self._placeholder_visible()
        self._sync_caret()

    def _on_placeholder_click(self, _event=None) -> str:
        """点占位文字等于点输入框：转焦点过去，让用户直接开打。"""
        try:
            self._entry.focus_set()
        except tk.TclError:
            pass
        return "break"

    def _on_entry_blur(self, _event=None) -> None:
        self._placeholder_visible()

    def _on_entry_text(self, _event=None) -> None:
        """输入内容变化时同步占位文字与光标（含代码写入的情况）。"""
        self._placeholder_visible()
        self._sync_caret()

    def _sync_caret(self, _event=None) -> None:
        """输入框空着且没有焦点时把光标宽度设成 0，免得它压住占位文字。"""
        try:
            focused = self._entry.focus_get() is self._entry
        except (tk.TclError, KeyError):
            focused = False
        width = 2 if (focused or self._entry_var.get().strip()) else 0
        try:
            self._entry.configure(insertwidth=width)
        except tk.TclError:
            pass

    # ------------------------------------------------------------ 公共接口

    def set_type(self, project_type: str) -> None:
        """切换内容类型（mod / resourcepack / shader / modpack），同时清空两栏。

        切换时会连输入框一起清空：模组页搜的是「小地图」，切到整合包还拿这个词
        去搜只会在整合包里搜出 3 个莫名其妙的包，标题上还留着上一个页签的关键词。
        用户的预期是「换页签 = 换一件事做」，所以从空白开始。
        """
        key = project_type if project_type in modrinth.CONTENT_TYPES else "mod"
        if key == self._ptype:
            return
        self._ptype = key
        self._reset_lists()
        try:
            self._entry_var.set("")
        except tk.TclError:
            return
        self._sync_type_ui()
        self._set_status(f"正在获取热门{self._type_name()}…")

    def set_context(self, game_version: str = None, loader: str = None,
                    target=None) -> None:
        """更新筛选上下文；某项传 None 表示沿用当前值。

        ``target`` 是下载落地目录（实例隔离时是实例目录），传 None 时保持
        不变；想回到全局 game_dir 就显式传 ``self.app.cfg.game_dir``。
        """
        if game_version is not None:
            self._game_version = (game_version or "").strip()
            try:
                self._ver_var.set(self._game_version)
                self._sync_version_select()
            except tk.TclError:
                return
        if loader is not None:
            self._loader = loader if loader in modrinth.LOADERS else ""
            try:
                self._loader_btn.set_text(_LOADER_TEXT[self._loader])
            except tk.TclError:
                return
        if target is not None:
            self._target = Path(target)
        if self._entry_var.get().strip():
            self._set_status("筛选条件已更新，点「搜索」重新查询")
        else:
            self._set_status(f"正在获取热门{self._type_name()}…")

    def refresh(self) -> None:
        """重新拉取当前关键字；没有关键字时直接列热门。

        反馈⑨：「不搜索就不显示结果」——用户以为界面坏了。没有关键字时
        改为请求 Modrinth 的热门列表（``index=downloads`` 且不带 query），
        一进来就有内容可点。
        """
        if self._busy:
            return
        self.do_search()

    def browse(self) -> None:
        """列出当前类型的热门内容（无关键字）。"""
        self._entry_var.set("")
        self.do_search()

    # ------------------------------------------------------------ 内部工具

    def _type_name(self) -> str:
        return modrinth.CONTENT_TYPES.get(self._ptype, ("mods", "内容"))[1]

    def _version_values(self) -> list[str]:
        """版本下拉的选项：全部 + 本机已装版本。

        上游清单（几百个）不适合塞进下拉，这里只列本机 ``versions`` 目录里
        真正能用的版本，加上「全部版本」；用户在搜索栏输入 1.20 这类关键字
        仍然照常生效。
        """
        out = [ALL_VERSIONS]
        try:
            from pathlib import Path as _P
            from ..launcher import list_installed_versions

            for vid in list_installed_versions(_P(str(self.app.cfg.game_dir))):
                if vid not in out:
                    out.append(vid)
        except Exception:                            # noqa: BLE001
            pass
        cur = (self._game_version or "").strip()
        if cur and cur not in out:
            out.insert(1, cur)
        return out

    def _sync_version_select(self) -> None:
        cur = (self._game_version or "").strip() or ALL_VERSIONS
        try:
            self._ver_sel.set_values(self._version_values())
            self._ver_sel.set(cur)
        except (tk.TclError, AttributeError):
            pass

    def _on_version_pick(self, value: str) -> None:
        self._game_version = "" if value == ALL_VERSIONS else value
        try:
            self._ver_var.set(self._game_version)
        except tk.TclError:
            pass
        if self._entry_var.get().strip():
            self.do_search()

    def _base_dir(self):
        """下载落地根目录：优先用外部传入的 target，否则用全局游戏目录。"""
        if self._target:
            return self._target
        return self.app.cfg.game_dir

    def _alive(self) -> bool:
        """组件是否还活着（被宿主切走/销毁后就把回调丢掉）。"""
        try:
            return bool(self.winfo_exists())
        except tk.TclError:
            return False

    def _post(self, fn) -> None:
        """把回调排到 UI 线程；组件已销毁则静默丢弃。"""
        def guarded() -> None:
            if not self._alive():
                return
            try:
                fn()
            except tk.TclError:
                pass

        try:
            self.app.post(guarded)
        except Exception:                            # noqa: BLE001
            pass

    def _log(self, message: str) -> None:
        """写日志：宿主给的回调可能直接操作控件，所以统一切回 UI 线程。"""
        cb = self._on_log
        if cb is None:
            return
        if threading.current_thread() is threading.main_thread():
            try:
                cb(message)
            except Exception:                        # noqa: BLE001
                pass
            return

        def emit() -> None:
            try:
                cb(message)
            except Exception:                        # noqa: BLE001
                pass

        self._post(emit)

    def _set_status(self, text: str, kind: str = "info") -> None:
        color = {"ok": SUCCESS, "warn": WARN, "err": DANGER}.get(kind, FG_FAINT)
        try:
            self._status.configure(text=text, fg=color)
        except tk.TclError:
            pass

    def _sync_type_ui(self) -> None:
        """按当前内容类型刷新按钮样式、提示语、占位符与左栏标题。"""
        for k, btn in self._type_btns.items():
            btn.kind = "primary" if k == self._ptype else "ghost"
            btn._draw()
        name = self._type_name()
        try:
            self._kind_hint.configure(text=_TYPE_HINT.get(self._ptype, ""))
            self._entry_ph = _TYPE_PLACEHOLDER.get(self._ptype, f"搜索{name}")
            self._ph.configure(text=self._entry_ph)
            self._placeholder_visible()
            self._lhead.configure(text=f"{name}搜索结果")
            # 整合包不是「下载到目录」，是下载后装成一个新版本，
            # 按钮文案得说清楚，否则用户以为下完就有了。
            self._dl_btn.set_text("下载并安装" if self._ptype == "modpack"
                                  else "下载所选")
            # 左栏右栏都清空，别让上一个页签的项目/版本残留在列表里
            self._reset_lists()
        except tk.TclError:
            return
        self._sync_loader_btn()

    def _sync_loader_btn(self) -> None:
        """加载器按钮在「模组」和「整合包」下出现，且始终排在「搜索」左边。

        整合包也按加载器过滤很有用：同一个整合包通常同时发 Fabric / Forge
        两个分支，选错了装完就起不来。
        """
        want = self._ptype in ("mod", "modpack")
        try:
            if want and not self._loader_visible:
                self._loader_btn.pack(side="left", padx=(8, 0), before=self._search_btn)
                self._loader_visible = True
            elif not want and self._loader_visible:
                self._loader_btn.pack_forget()
                self._loader_visible = False
        except tk.TclError:
            pass

    def _cycle_loader(self) -> None:
        i = _LOADER_CYCLE.index(self._loader) if self._loader in _LOADER_CYCLE else 0
        self._loader = _LOADER_CYCLE[(i + 1) % len(_LOADER_CYCLE)]
        self._loader_btn.set_text(_LOADER_TEXT[self._loader])

    def _open_folder(self) -> None:
        try:
            if self._ptype == "modpack":
                # 整合包不落进游戏目录：下到临时目录后立刻解包成版本
                import tempfile

                folder = Path(tempfile.gettempdir()) / "MCLite" / "packs"
                folder.mkdir(parents=True, exist_ok=True)
                open_folder(folder)
                return
            open_folder(modrinth.target_dir(self._base_dir(), self._ptype))
        except Exception as exc:                     # noqa: BLE001
            self._set_status(f"打开目录失败：{exc}", "err")

    def _clear(self, scroll: ScrollFrame) -> None:
        for w in scroll.inner.winfo_children():
            w.destroy()

    def _reset_lists(self) -> None:
        """清空两栏与选择状态，下载按钮回到不可用。"""
        self._gen += 1
        self._clear(self._lscroll)
        self._clear(self._rscroll)
        self._rows.clear()
        self._vrows.clear()
        self._projects = []
        self._versions = []
        self._project = None
        self._version = None
        try:
            self._rhead.configure(text="版本文件")
            self._lhead.configure(text=f"{self._type_name()}搜索结果")
            self._dl_btn.set_enabled(False)
        except tk.TclError:
            pass

    # ------------------------------------------------------------ 搜索

    def do_search(self) -> None:
        """按输入框内容搜索；空关键字时列出热门内容。

        反馈⑨：原来 ``if not query: return`` 让下载页一进来就是空白，用户
        以为「不能下载」。现在空关键字直接查热门（``index=downloads`` 不带
        query 就是按下载量排序的榜单）。
        """
        if self._busy:
            return
        query = self._entry_var.get().strip()
        english, hint = query, ""
        if query:
            from .. import cnsearch
            english, hint = cnsearch.translate(query)
            if not english:
                self._set_status(f"没认出「{query}」里的中文关键词，换个说法试试"
                                 f"（比如「小地图」「优化」「钠」）", "warn")
                return

        self._busy = True
        self._reset_lists()
        gen = self._gen
        if query:
            self._lhead.configure(text=f"搜索 “{query}” 中…")
            self._set_status(f"中文关键词：{hint} → 按 “{english}” 搜索" if hint
                             else "正在请求 Modrinth…")
        else:
            self._lhead.configure(text=f"热门{self._type_name()} 加载中…")
            self._set_status("正在获取热门内容…")

        gv = self._ver_var.get().strip()
        # 整合包也要按加载器过滤：同一个包常同时发 Fabric / Forge 分支，
        # 不过滤的话选了 Forge 也会混进一堆 Fabric 包。
        loader = self._loader if self._ptype in ("mod", "modpack") else ""

        def work() -> None:
            try:
                hits, total = modrinth.search(english, gv, loader, limit=25,
                                              project_type=self._ptype,
                                              index="relevance" if query else "downloads")
            except Exception as exc:                 # noqa: BLE001
                # 注意：except 块结束后 exc 会被删掉，必须先把字符串取出来
                err = f"{type(exc).__name__}: {exc}"
                self._post(lambda: self._search_done(None, 0, err, _gen=gen))
                return
            renamed = f"{query} → {english}" if hint else ""
            self._post(lambda: self._search_done(hits, total, "", renamed, _gen=gen))

        threading.Thread(target=work, daemon=True).start()

    def _search_done(self, hits, total: int, error: str, renamed: str = "",
                     _gen: int = None) -> None:
        if _gen is not None and _gen != self._gen:
            return                                   # 过期结果，当前列表已经换了内容
        self._busy = False
        if error or hits is None:
            self._lhead.configure(text="搜索失败")
            self._set_status(f"搜索失败：{error}", "err")
            self._log(f"Modrinth 搜索失败：{error}")
            return
        self._projects = list(hits)
        suffix = f"（{renamed}）" if renamed else ""
        if self._entry_var.get().strip():
            self._lhead.configure(text=f"搜索结果{suffix}（{total} 个，显示 {len(hits)} 个）")
            self._set_status(f"共 {total} 个结果，点左边选一个查看版本")
        else:
            self._lhead.configure(text=f"热门{self._type_name()}（显示 {len(hits)} 个）")
            self._set_status("这是按下载量排序的热门内容，输入关键字可以精确搜索")
        try:
            self._lscroll.scroll_to_top()
        except tk.TclError:
            pass
        if not hits:
            box = tk.Frame(self._lscroll.inner, bg=BG_ALT)
            box.pack(fill="x", pady=40)
            tk.Label(box, text="没有找到匹配的内容", bg=BG_ALT, fg=FG_DIM,
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
        self._gen += 1                                # 让上一个项目的版本请求作废
        self._vrows.clear()
        self._versions = []
        self._version = None
        self._dl_btn.set_enabled(False)

        gv = self._ver_var.get().strip()
        loader = self._loader if self._ptype in ("mod", "modpack") else ""
        gen = self._gen

        def work() -> None:
            try:
                vs = modrinth.versions(p.project_id, gv, loader)
            except Exception as exc:                 # noqa: BLE001
                err = f"{type(exc).__name__}: {exc}"
                self._post(lambda: self._versions_done([], err, _gen=gen))
                return
            self._post(lambda: self._versions_done(vs, "", _gen=gen))

        threading.Thread(target=work, daemon=True).start()

    def _versions_done(self, vs, error: str, _gen: int = None) -> None:
        if _gen is not None and _gen != self._gen:
            return                                   # 已经换了别的项目
        self._versions = list(vs)
        if error:
            self._set_status(f"获取版本失败：{error}", "err")
            self._log(f"获取版本失败：{error}")
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
        try:
            self._rscroll.scroll_to_top()
        except tk.TclError:
            pass
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
                 font=self.app.fonts["small"]).pack(fill="x")

        f = modrinth.primary_file(v)
        color = {"release": SUCCESS, "beta": WARN, "alpha": DANGER}.get(
            f.release_type if f else "release", FG_FAINT)
        tk.Label(row.inner, text=f.size_label if f else "?", bg=BG_ALT, fg=color,
                 width=9, anchor="e", font=self.app.fonts["small"]).pack(side="right")

        row.attach()
        self._vrows[v.version_id] = row

    def _pick_version(self, v: modrinth.ModVersion) -> None:
        self._version = v
        for k, row in self._vrows.items():
            row.set_selected(k == v.version_id)
        f = modrinth.primary_file(v)
        if f:
            self._set_status(f"已选择 {v.version_number} → {f.filename}（{f.size_label}）")
        else:
            self._set_status("这个版本没有可下载的文件", "warn")
        self._dl_btn.set_enabled(bool(f))

    # ------------------------------------------------------------ 下载

    def download_selected(self) -> None:
        """下载当前选中的版本文件。

        普通内容（模组 / 资源包 / 光影）直接落进对应目录；
        整合包是个例外：它要先下到临时目录，再交给 ``PackInstallDialog``
        解包成一个独立版本 —— 丢进 ``modpacks`` 目录没人会去装它。
        """
        if not self._version:
            return
        f = modrinth.primary_file(self._version)
        if not f:
            self._set_status("这个版本没有可下载的文件", "err")
            return
        if self._ptype == "modpack":
            self._fetch_pack(f)
            return
        target = modrinth.target_dir(self._base_dir(), self._ptype)

        self._dl_btn.set_enabled(False)
        self._progress.pack(side="right", fill="x", expand=True, padx=(16, 16))
        self._progress.set(0.0)
        self._set_status(f"正在下载 {f.filename} …")
        self._log(f"开始下载 {f.filename} → {target}")

        last = [0.0]
        stop = threading.Event()

        def tick(progress: Progress) -> None:
            now = time.time()
            if now - last[0] < 0.1 or stop.is_set():
                return
            last[0] = now
            pct, _cur, _speed = progress.snapshot()
            self._post(lambda: self._progress.set(pct))

        def finish(ok: int, bad: int, error: str = "") -> None:
            stop.set()
            self._post(lambda: self._download_done(ok, bad, f, error))

        def work() -> None:
            try:
                ok, bad = modrinth.download(
                    [f], target,
                    progress_cb=lambda p: tick(p),
                    on_log=self._log,
                )
            except Exception as exc:                 # noqa: BLE001
                finish(0, 1, f"{type(exc).__name__}: {exc}")
                return
            finish(ok, bad)

        threading.Thread(target=work, daemon=True).start()

    def _fetch_pack(self, f: modrinth.ModFile) -> None:
        """整合包：下到临时目录，完成后弹安装窗口解包成版本。"""
        import tempfile

        from ..downloader import Downloader, DownloadTask

        temp = Path(tempfile.gettempdir()) / "MCLite" / "packs"
        temp.mkdir(parents=True, exist_ok=True)
        dest = temp / (f.filename or "pack.mrpack")

        self._dl_btn.set_enabled(False)
        self._progress.pack(side="right", fill="x", expand=True, padx=(16, 16))
        self._progress.set(0.0)
        self._set_status(f"正在下载整合包 {f.filename} …")
        self._log(f"开始下载整合包 {f.filename}（{f.size_label}）")

        last = [0.0]

        def tick(progress: Progress) -> None:
            now = time.time()
            if now - last[0] < 0.1:
                return
            last[0] = now
            pct, _cur, _speed = progress.snapshot()
            self._post(lambda: self._progress.set(pct))

        def work() -> None:
            try:
                task = DownloadTask(url=f.url, dest=dest, sha1=f.sha1 or None,
                                    size=f.size or None)
                ok, bad = Downloader(threads=4).run(
                    [task], source="official",
                    progress_cb=lambda p: tick(p), on_log=self._log)
            except Exception as exc:                 # noqa: BLE001
                self._post(lambda: self._pack_failed(f"{type(exc).__name__}: {exc}"))
                return
            if not ok or bad:
                self._post(lambda: self._pack_failed("下载失败，检查网络或换一个下载源"))
                return
            self._post(lambda: self._pack_ready(dest, f))

        threading.Thread(target=work, daemon=True).start()

    def _pack_failed(self, msg: str) -> None:
        try:
            self._progress.pack_forget()
            self._dl_btn.set_enabled(True)
        except tk.TclError:
            return
        self._set_status(f"整合包下载失败：{msg}", "err")
        self._log(f"整合包下载失败：{msg}")

    def _pack_ready(self, dest: Path, f: modrinth.ModFile) -> None:
        """下载完了：开安装窗口把它解成一个版本。"""
        try:
            self._progress.pack_forget()
            self._dl_btn.set_enabled(True)
        except tk.TclError:
            pass
        self._set_status(f"已下载 {f.filename}，正在解包安装…", "ok")
        self._log(f"已下载到 {dest}，开始解包安装")
        try:
            from .pack_dialog import PackInstallDialog
        except Exception as exc:                     # noqa: BLE001
            self._set_status(f"打不开安装窗口：{exc}", "err")
            return
        base = ""
        home = getattr(self.app, "_pages", {}).get("home")
        if home is not None:
            base = str(getattr(home, "_selected", "") or "")
        dlg = PackInstallDialog(self.app, dest, on_done=self._on_pack_done,
                                base_version=base)
        try:
            dlg.grab_set()
        except tk.TclError:
            pass

    def _on_pack_done(self, vid: str) -> None:
        """整合包装完了：通知开始页刷新列表并选中它。"""
        self._set_status(f"整合包已装成版本「{vid}」，到开始页就能启动", "ok")
        self._log(f"✔ 整合包已装成版本「{vid}」")
        home = getattr(self.app, "_pages", {}).get("home")
        if home is None:
            return
        try:
            home.reload_versions()
            home._select(vid)
        except Exception:                            # noqa: BLE001
            pass
        notify = getattr(self.app, "notify", None)
        if notify:
            try:
                notify(f"整合包已就绪：{vid}", "ok")
            except Exception:                        # noqa: BLE001
                pass

    def _download_done(self, ok: int, bad: int, f: modrinth.ModFile,
                       error: str = "") -> None:
        try:
            self._progress.pack_forget()
            self._dl_btn.set_enabled(bool(self._version))
        except tk.TclError:
            return
        if error:
            self._set_status(f"下载失败：{error}", "err")
            self._log(f"下载失败：{error}")
            return
        if ok and not bad:
            folder = modrinth.CONTENT_TYPES.get(self._ptype, ("mods", ""))[0]
            self._set_status(f"已安装到 {folder}：{f.filename}", "ok")
            self._log(f"已安装到 {folder}：{f.filename}")
            notify = getattr(self.app, "notify", None)
            if notify:
                try:
                    notify(f"已下载 {f.filename}", "ok")
                except Exception:                    # noqa: BLE001
                    pass
        else:
            self._set_status(f"下载失败（{bad} 个文件）", "err")
            self._log(f"下载失败：{f.filename}（{bad} 个文件）")
