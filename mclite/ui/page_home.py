"""开始页：版本选择、启动按钮、日志。"""

from __future__ import annotations

import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from .. import APP_NAME
from .. import auth, crash
from .. import instances, javaauto, modpack, skin_sites
from ..java import detect_all, pick_for_version, required_java
from ..launcher import (
    GameLauncher,
    LaunchError,
    LaunchOptions,
    list_installed_versions,
    offline_uuid,
    version_meta,
)
from . import images, responsive
from .theme import (
    ACCENT, BG, BG_ALT, BG_HOVER, BORDER, DANGER, FG, FG_DIM, FG_FAINT,
    SUCCESS, WARN, FlatButton, ScrollFrame, Slider, round_rect,
)
from .widgets import LogPanel, Page, ProgressBar, SelectableRow, TabBar

#: 首页内部页签：启动 / 模组 / 账户。
#: 模组和账户原本一个是独立导航页、一个是弹窗，用户反馈「单开一页/单开弹窗不方便」。
HOME_TABS = [
    ("launch",  "启动"),
    ("mods",    "模组"),
    ("account", "账户"),
]

#: 左栏（已安装版本列表）的默认宽度。窗口变窄时由 _on_width 收窄，见 responsive.left_width。
LEFT_W = 380
#: 左栏收窄的下限。再窄版本号 + 类型/日期两行就换不动了。
LEFT_W_MIN = 232


class HomePage(Page):
    title = "开始"

    def build(self) -> None:
        self._selected: str | None = None
        self._rows: dict[str, SelectableRow] = {}
        self._proc = None
        self._launching = False
        self._tail_stop: threading.Event | None = None
        self._mods_panel = None
        self._accounts_panel = None
        self._warm_scheduled = False
        #: 启动日志默认收起，把右半边让给启动面板（用户反馈「日志完全可以隐藏起来」）
        self._log_open = False

        shell = tk.Frame(self, bg=BG)
        shell.pack(fill="both", expand=True)

        tabs_row = tk.Frame(shell, bg=BG)
        tabs_row.pack(fill="x", padx=24, pady=(10, 0))
        self._tabs = TabBar(tabs_row, HOME_TABS, on_change=self._on_tab, bg=BG,
                            height=38, gap=28,
                            font=("Microsoft YaHei UI", 11),
                            font_active=("Microsoft YaHei UI", 11, "bold"))
        self._tabs.pack(side="left")

        self._stack = tk.Frame(shell, bg=BG)
        self._stack.pack(fill="both", expand=True)

        # 三个页签用 place 叠在同一个位置，切换只 lift。用 pack 的话每次切换
        # 都要把 100 多行列表重新算一遍布局（实测 ~400ms），表现就是用户说的
        # "切换页面比较卡"。
        #
        # 但**没显示的页签要 place_forget**：窗口拉伸时 Tk 会重排所有已 place
        # 的树，三个页签叠着一起算实测要从 90ms 涨到 130ms+（用户反馈「页面
        # 拉伸的时候很卡」）。重新 place 回来只要几毫秒。
        self._tab_launch = tk.Frame(self._stack, bg=BG)
        self._tab_mods = tk.Frame(self._stack, bg=BG)
        self._tab_account = tk.Frame(self._stack, bg=BG)
        self._tab_launch.place(x=0, y=0, relwidth=1, relheight=1)

        root = tk.Frame(self._tab_launch, bg=BG)
        root.pack(fill="both", expand=True, padx=24, pady=(8, 12))

        # ---------------- 顶部主视觉（ComfyUI 出的浮岛插画，文字压在左侧深蓝上）
        head = tk.Frame(root, bg=BG)
        head.pack(fill="x")
        hero = images.load(self, "hero")
        self._hero = hero
        self._hero_canvas = None
        if hero is not None:
            canvas = tk.Canvas(head, width=hero.width(), height=hero.height(),
                               bg=BG, highlightthickness=0, bd=0)
            canvas.pack(side="left", anchor="nw")
            canvas.create_image(0, 0, anchor="nw", image=hero)
            canvas.image = hero
            canvas.create_text(30, 32, text="启动 Minecraft", anchor="w",
                               fill="#FFFFFF",
                               font=("Microsoft YaHei UI", 19, "bold"))
            canvas.create_text(31, 64, text="选一个版本，点一下就能进游戏", anchor="w",
                               fill="#CFE3FA", font=self.app.fonts["body"])
            self._hero_canvas = canvas
        else:
            tk.Label(head, text="启动 Minecraft", bg=BG, fg=FG,
                     font=self.app.fonts["h1"]).pack(side="left")

        # ---------------- 主体：左右分栏
        body = tk.Frame(root, bg=BG)
        body.pack(fill="both", expand=True, pady=(14, 0))
        self._body = body
        self._root_frame = root

        # 左：版本列表
        left = tk.Frame(body, bg=BG_ALT, width=LEFT_W)
        left.pack(side="left", fill="both", expand=False)
        left.pack_propagate(False)
        self._left = left

        bar = tk.Frame(left, bg=BG_ALT, height=44)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Label(bar, text="已安装版本", bg=BG_ALT, fg=FG,
                 font=self.app.fonts["h2"]).pack(side="left", padx=14, pady=10)
        refresh_btn = FlatButton(bar, "刷新", command=self.reload_versions,
                                 kind="ghost", height=26, font=self.app.fonts["small"],
                                 bg=BG_ALT)
        refresh_btn.pack(side="right", padx=10, pady=9)

        tk.Frame(left, bg=BORDER, height=1).pack(fill="x")

        # 左下角原来还有一行「把 .jar / .zip / .mrpack 拖进窗口即可安装」，
        # 用户反馈「这一行完全可以不要」——拖拽照旧支持，只去掉这行占地方的提示。
        self._scroll = ScrollFrame(left, bg=BG_ALT)
        self._scroll.pack(fill="both", expand=True)

        # 右：启动面板
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(18, 0))
        self._right = right

        # 启动/结束游戏这两个按钮钉在右栏底部：它们是最常用的操作，
        # 不能因为窗口压矮就要先滚动才找得到。必须**先** pack 它们（side=bottom）
        # 再 pack 滚动区，否则 fill+expand 的滚动区会先把空腔吃光。
        self._actions_slot = tk.Frame(right, bg=BG_ALT)
        self._actions_slot.pack(side="bottom", fill="x")

        # 启动面板放进可滚动容器：窗口压矮时（882x560 实测右栏要 444px、只剩
        # 330px）原来「启动游戏」按钮会整块掉到窗口外面，用户反馈「往小调整
        # 窗口的时候按键要能完整显示」。现在是滚起来就能看到，一个都不少。
        self._right_scroll = ScrollFrame(right, bg=BG)
        self._right_scroll.pack(fill="both", expand=True)
        panel_parent = self._right_scroll.inner

        panel = tk.Frame(panel_parent, bg=BG_ALT)
        panel.pack(fill="x")
        self._panel = panel

        info = tk.Frame(panel, bg=BG_ALT, padx=18, pady=16)
        info.pack(fill="x")

        self._big_name = tk.Label(info, text="未选择版本", bg=BG_ALT, fg=FG,
                                  font=("Segoe UI", 20, "bold"), anchor="w")
        self._big_name.pack(fill="x")
        self._big_sub = tk.Label(info, text="从左侧选择一个版本", bg=BG_ALT, fg=FG_DIM,
                                 font=self.app.fonts["small"], anchor="w")
        self._big_sub.pack(fill="x", pady=(4, 0))
        # 游戏目录路径挪进面板：原来浮在 hero 右上角，和版本信息分居两处
        # （用户反馈「这个路径可以和游戏路径放在一起」）。现在它是这一块的
        # 第三行，点一下直接打开目录，下面那排按钮就不用再放一个「游戏目录」。
        self._dir_label = tk.Label(info, text="", bg=BG_ALT, fg=FG_FAINT, anchor="w",
                                   font=self.app.fonts["small"], cursor="hand2")
        self._dir_label.pack(fill="x", pady=(6, 0))
        self._dir_label.bind("<Button-1>", lambda _e: self._open_dir())
        self._dir_label.bind("<Enter>", lambda _e: self._dir_label.configure(fg=ACCENT))
        self._dir_label.bind("<Leave>", lambda _e: self._dir_label.configure(fg=FG_FAINT))

        tk.Frame(panel, bg=BORDER, height=1).pack(fill="x", padx=18)

        opts = tk.Frame(panel, bg=BG_ALT, padx=18, pady=14)
        opts.pack(fill="x")

        row1 = tk.Frame(opts, bg=BG_ALT)
        row1.pack(fill="x", pady=3)
        self._name_title = tk.Label(row1, text="玩家名", bg=BG_ALT, fg=FG_DIM, width=7,
                                    anchor="w", font=self.app.fonts["body"])
        self._name_title.pack(side="left")
        self._name_var = tk.StringVar(value=self.app.cfg.get("username") or "Steve")
        self._name_entry = tk.Entry(row1, textvariable=self._name_var, bg=BG, fg=FG,
                                    insertbackground=FG, bd=0, highlightthickness=1,
                                    highlightbackground=BORDER, highlightcolor=ACCENT,
                                    disabledbackground=BG, disabledforeground=FG_DIM,
                                    font=self.app.fonts["body"])
        self._name_entry.pack(side="left", fill="x", expand=True, ipady=4)
        self._name_entry.bind("<FocusOut>", self._on_name_change)
        # 账户入口统一到「账户」页签与右上角胶囊，这里不再放第二个「账号管理」按钮；
        # 有正版/皮肤站账号时这一行直接锁住并说明名字由账号决定（反馈⑥）
        self._acc_hint = tk.Label(row1, text="", bg=BG_ALT, fg=FG_FAINT,
                                  font=self.app.fonts["small"])
        self._acc_hint.pack(side="right", padx=(8, 0))

        row2 = tk.Frame(opts, bg=BG_ALT)
        row2.pack(fill="x", pady=3)
        tk.Label(row2, text="Java", bg=BG_ALT, fg=FG_DIM, width=7, anchor="w",
                 font=self.app.fonts["body"]).pack(side="left")
        # 右侧按钮先 pack：否则左边 Label 的请求宽度会把按钮挤出可视区
        FlatButton(row2, "重新检测", command=self._refresh_java, kind="ghost",
                   height=24, font=self.app.fonts["small"], bg=BG_ALT).pack(side="right")
        self._java_label = tk.Label(row2, text="检测中…", bg=BG_ALT, fg=FG_DIM,
                                    font=self.app.fonts["small"], anchor="w")
        self._java_label.pack(side="left", fill="x", expand=True)

        row3 = tk.Frame(opts, bg=BG_ALT)
        row3.pack(fill="x", pady=3)
        tk.Label(row3, text="内存", bg=BG_ALT, fg=FG_DIM, width=7, anchor="w",
                 font=self.app.fonts["body"]).pack(side="left")
        self._mem_var = tk.IntVar(value=int(self.app.cfg.get("memory_mb") or 4096))
        self._mem_slider = Slider(row3, 1024, 16384, self._mem_var.get(), step=512,
                                  command=lambda v: self._on_mem_change(v),
                                  width=260, suffix=" MB", bg=BG_ALT)
        self._mem_slider.pack(side="left", fill="x", expand=True)

        # 启动按钮（「游戏目录」按钮去掉了：路径就在上方第三行，点它即可打开）
        # 挂在 _actions_slot 上（钉在右栏底部），不在滚动区里 —— 窗口再矮也点得到。
        actions = tk.Frame(self._actions_slot, bg=BG_ALT, padx=18, pady=12)
        actions.pack(fill="x")
        self._actions = actions
        self._launch_btn = FlatButton(actions, "启动游戏", command=self.launch,
                                      kind="primary", height=40, width=132,
                                      font=("Microsoft YaHei UI", 11, "bold"), bg=BG_ALT)
        self._launch_btn.pack(side="left")
        self._stop_btn = FlatButton(actions, "结束游戏", command=self._stop_game,
                                    kind="danger", height=40, width=92, bg=BG_ALT)
        self._stop_btn.pack(side="left", padx=8)
        self._stop_btn.set_enabled(False)

        # 实例管理
        # 这五个按钮原来是 pack(side="left") 横排，窗口一窄就被推出窗口外（用户
        # 反馈「往小调整窗口时按键要完整显示」）。改用 FlowRow，放不下自动换行。
        manage = responsive.FlowRow(panel_parent, gap=6, row_gap=6, bg=BG_ALT)
        manage.pack(fill="x", padx=18, pady=(0, 12))
        self._manage = manage
        self._delete_btn = FlatButton(manage, "删除版本", command=self._delete_version,
                                      kind="danger", height=28, width=90,
                                      font=self.app.fonts["small"], bg=BG_ALT)
        self._delete_btn.set_enabled(False)
        self._world_btn = FlatButton(manage, "存档", command=self._open_worlds,
                                     kind="ghost", height=28, width=56,
                                     font=self.app.fonts["small"], bg=BG_ALT)
        self._verify_btn = FlatButton(manage, "校验", command=self._open_verify,
                                      kind="ghost", height=28, width=56,
                                      font=self.app.fonts["small"], bg=BG_ALT)
        self._export_btn = FlatButton(manage, "导出", command=self._export_pack,
                                      kind="ghost", height=28, width=56,
                                      font=self.app.fonts["small"], bg=BG_ALT)
        self._log_btn = FlatButton(manage, "日志", command=self._open_logs, kind="ghost",
                                   height=28, width=56, font=self.app.fonts["small"],
                                   bg=BG_ALT)
        manage.add_all(self._delete_btn, self._world_btn, self._verify_btn,
                       self._export_btn, self._log_btn)
        for btn in (self._world_btn, self._verify_btn, self._export_btn):
            btn.set_enabled(False)

        # 日志（可折叠：默认收起，只留一行标题；点标题展开看实时输出）
        log_card = tk.Frame(panel_parent, bg=BG_ALT)
        log_card.pack(fill="x", pady=(14, 0))
        self._log_card = log_card
        lb = tk.Frame(log_card, bg=BG_ALT, height=34)
        lb.pack(fill="x")
        lb.pack_propagate(False)
        self._log_toggle = tk.Label(lb, text="▸  启动日志", bg=BG_ALT, fg=FG_DIM,
                                    font=self.app.fonts["small"], cursor="hand2")
        self._log_toggle.pack(side="left", padx=12, pady=8)
        self._log_toggle.bind("<Button-1>", lambda _e: self._toggle_log())
        FlatButton(lb, "清空", command=lambda: self._log.clear(), kind="ghost",
                   height=22, font=self.app.fonts["small"], bg=BG_ALT,
                   width=56).pack(side="right", padx=8, pady=6)
        tk.Frame(log_card, bg=BORDER, height=1).pack(fill="x")
        self._log_body = tk.Frame(log_card, bg=BG_ALT)
        self._log = LogPanel(self._log_body, height=8)
        self._log.pack(fill="both", expand=True)
        if self._log_open:
            self._log_body.pack(fill="both", expand=True)

        self._javas = []
        self._last_w = 0
        self.after(150, self.reload_versions)
        self.after(300, self._refresh_java)
        self.after(120, self.on_account_changed)

    # ------------------------------------------------------------ 自适应宽度

    def on_resize(self, width: int) -> None:
        """按页面宽度重排：收窄左栏、裁掉主视觉右边、给长版本名换行、按钮行自动换行。

        用户反馈「在往小调整窗口的时候自动调整分辨率使按键能够完整显示」。
        原来左栏固定 380、主视觉固定 820、版本名不换行，窗口一窄右栏就被挤到
        窗口外面（880x560 实测 21 个控件被压，最狠的一行想要 820 只有 603）。
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
        # 注意这里要减掉页面左右各 24px 的内边距：页面 651 宽时 body 只有 603，
        # 右栏实际是 603-232-18=353。早先按页面宽度算，算出的 401 比真实宽 48，
        # 版本号 wraplength 设成 365 就还是会被父框裁掉 35px。
        body_w = max(200, w - 48)
        right_w = max(200, body_w - left_w - 18)

        # 主视觉（820x104 的插画）：窄了就把画布本身收窄，图像超出部分自然被裁。
        # 不去缩放图片——subsample 只能整数倍，缩出来会糊，而左边压着的两行字才是
        # 要保住的东西。
        hero_canvas = getattr(self, "_hero_canvas", None)
        if hero_canvas is not None:
            avail = max(320, w - 48)
            try:
                hero_canvas.configure(width=min(self._hero.width(), avail))
            except (tk.TclError, AttributeError):
                pass

        # 版本名：Segoe UI 20 太宽，窄窗口时降字号 + 允许换行，否则会顶出右栏。
        size = 20 if right_w >= 380 else (17 if right_w >= 300 else 15)
        wrap = max(120, right_w - 36)
        try:
            self._big_name.configure(font=("Segoe UI", size, "bold"),
                                     wraplength=wrap)
            self._big_sub.configure(wraplength=wrap)
            self._dir_label.configure(wraplength=wrap)
        except (tk.TclError, AttributeError):
            pass

        manage = getattr(self, "_manage", None)
        if manage is not None:
            try:
                manage.reflow(right_w - 36)
            except tk.TclError:
                pass

        # 内存滑条是 Canvas，请求宽度写死 260；右栏窄到 353 时它只剩 248，
        # 于是「被压扁」报告就永远挂着。它不是按钮，压扁了照样能滑，只是
        # req>got 会让上层布局一直以为空间不够 —— 把请求宽度设成小值，
        # 实际宽度由 fill="x"/expand 决定，_on_resize 会按真实宽度重画。
        slider = getattr(self, "_mem_slider", None)
        if slider is not None:
            try:
                slider.configure(width=120)
            except tk.TclError:
                pass

        # 剩下的“被兄弟控件挤窄”的提示语交给兜底换行。排三次是因为改
        # wraplength 本身会改变布局，第一次量到的往往还是旧宽度。
        for delay in (60, 200, 500):
            try:
                self.after(delay, lambda: responsive.fix_clipped(self))
            except tk.TclError:
                break

    # ------------------------------------------------------------ 页签

    def _show_tab_frame(self, target: tk.Frame) -> None:
        """显示某个页签：其余页签 place_forget，目标页 place + lift。

        只 lift 不行——没显示过的页签本来就没 place，而窗口拉伸时未显示的页签
        被 place_forget 掉才不会有额外布局开销（用户反馈「页面拉伸的时候很卡」）。
        """
        for frame in (self._tab_launch, self._tab_mods, self._tab_account):
            if frame is target:
                continue
            try:
                frame.place_forget()
            except tk.TclError:
                pass
        if not target.winfo_manager():
            target.place(x=0, y=0, relwidth=1, relheight=1)
        target.lift()

    def _on_tab(self, key: str) -> None:
        """切换首页内部页签（启动 / 模组 / 账户）。"""
        if key == "mods":
            first_time = self._mods_panel is None
            self._ensure_mods_panel()
            self._show_tab_frame(self._tab_mods)
            if self._mods_panel is not None and not first_time:
                # 第一次建面板时构造函数里已经按当前版本 reload 过一次了，
                # 这里再 set_version + refresh 会把 100 多行列表连着重建两遍
                # （用户反馈「切换页面比较卡」，实测 3.5 秒就是这么来的）。
                try:
                    self._mods_panel.set_version(self._selected or "")
                except Exception:                    # noqa: BLE001
                    pass
        elif key == "account":
            self._ensure_accounts_panel()
            self._show_tab_frame(self._tab_account)
            if self._accounts_panel is not None:
                try:
                    self._accounts_panel.refresh()
                except Exception:                    # noqa: BLE001
                    pass
        else:
            self._show_tab_frame(self._tab_launch)
        # 页签切换后新出现的控件需要重新登记拖拽目标
        try:
            self.app.add_drop_target(self._stack)
        except Exception:                            # noqa: BLE001
            pass

    def _ensure_mods_panel(self) -> None:
        if self._mods_panel is not None:
            return
        from .mods_panel import ModsPanel
        root = tk.Frame(self._tab_mods, bg=BG)
        root.pack(fill="both", expand=True, padx=24, pady=(8, 14))
        self._mods_panel = ModsPanel(
            root, self.app,
            on_log=lambda m: self._log.write(m),
            on_download=self._open_download_tab)
        self._mods_panel.pack(fill="both", expand=True)
        self._mods_panel.set_version(self._selected or "")

    def _ensure_accounts_panel(self) -> None:
        if self._accounts_panel is not None:
            return
        from .accounts_panel import AccountsPanel
        root = tk.Frame(self._tab_account, bg=BG)
        root.pack(fill="both", expand=True, padx=24, pady=(8, 14))
        self._accounts_panel = AccountsPanel(root, self.app,
                                             on_log=lambda m: self._log.write(m))
        self._accounts_panel.pack(fill="both", expand=True)

    def show_tab(self, key: str) -> None:
        """外部（账户胶囊、Mod 页旧入口等）切到某个页签。"""
        self._tabs.set(key, fire=True)

    def _open_download_tab(self, project_type: str = "mod") -> None:
        """模组页签里的「下载」：切到下载页并打开对应内容的 Modrinth 浏览器。"""
        # mods_panel 传的是目录名（mods/resourcepacks/shaderpacks/datapacks），
        # download_browser 用的是 Modrinth 的 project_type（mod/resourcepack/shader）。
        alias = {
            "mods": "mod",
            "mod": "mod",
            "resourcepacks": "resourcepack",
            "resourcepack": "resourcepack",
            "shaderpacks": "shader",
            "shader": "shader",
            "modpacks": "modpack",
            "modpack": "modpack",
        }
        kind = alias.get(str(project_type or "").strip().lower(), "")
        if not kind:
            self.app.notify("这一类内容不支持在线下载，可以手动拖入文件", "warn")
            return
        self.app.show_page("install")
        page = self.app._pages.get("install")
        if page is not None and hasattr(page, "open_browser"):
            try:
                page.open_browser(kind)
            except Exception:                        # noqa: BLE001
                pass

    def _toggle_log(self, force: bool | None = None) -> None:
        """折叠 / 展开启动日志（用户反馈：日志占满右半边，应该能收起来）。"""
        if force is True:
            self._log_open = True
        elif force is False:
            self._log_open = False
        else:
            self._log_open = not self._log_open
        if self._log_open:
            self._log_card.pack_configure(fill="both", expand=True)
            self._log_body.pack(fill="both", expand=True)
            self._log_toggle.configure(text="▾  启动日志")
        else:
            self._log_body.pack_forget()
            self._log_card.pack_configure(fill="x", expand=False)
            self._log_toggle.configure(text="▸  启动日志")

    # ------------------------------------------------------------ 数据

    def on_show(self) -> None:
        self._dir_label.configure(text=str(self.app.cfg.game_dir))
        if not self._rows:
            self.reload_versions()
        # 首次点「模组」页签要现建面板 + 108 行列表，约 1.8 秒。启动后趁用户
        # 还在看首页时先建好，点下去就只剩一次 lift。
        if self._mods_panel is None and not self._warm_scheduled:
            self._warm_scheduled = True
            self.after(600, self._warm_mods_panel)

    def _warm_mods_panel(self) -> None:
        """后台预建模组面板：建好但不显示，也不抢焦点。"""
        if self._mods_panel is not None:
            return
        try:
            self._ensure_mods_panel()
        except Exception:                            # noqa: BLE001
            pass

    def reload_versions(self) -> None:
        for w in self._scroll.inner.winfo_children():
            w.destroy()
        self._rows.clear()
        self._selected = None
        self._delete_btn.set_enabled(False)
        for btn in (getattr(self, "_world_btn", None), getattr(self, "_verify_btn", None),
                    getattr(self, "_export_btn", None)):
            if btn is not None:
                btn.set_enabled(False)
        game_dir = self.app.cfg.game_dir
        versions = list_installed_versions(game_dir)

        if not versions:
            box = tk.Frame(self._scroll.inner, bg=BG_ALT, pady=26)
            box.pack(fill="x")
            art = images.load(self, "empty-versions")
            if art is not None:
                cap = tk.Label(box, image=art, bg=BG_ALT, bd=0)
                cap.image = art
                cap.pack()
            tk.Label(box, text="还没有安装任何版本", bg=BG_ALT, fg=FG_DIM,
                     font=self.app.fonts["body"]).pack(pady=(10, 0))
            tk.Label(box, text="去「下载」页装一个吧", bg=BG_ALT, fg=FG_FAINT,
                     font=self.app.fonts["small"]).pack(pady=(4, 0))
            self._big_name.configure(text="未选择版本")
            self._big_sub.configure(text="没有可用的版本")
            return

        for vid in versions:
            self._add_row(vid)

        # 默认选中第一个
        if versions:
            self._select(versions[0])

    def _add_row(self, vid: str) -> None:
        meta = version_meta(self.app.cfg.game_dir, vid)
        row = SelectableRow(self._scroll.inner, on_click=lambda v=vid: self._select(v),
                            bg=BG_ALT, pad=9)
        row.pack(fill="x")

        # 版本类型色条
        kind = meta.get("type") or "?"
        color = {"release": SUCCESS, "snapshot": WARN, "old_beta": FG_FAINT,
                 "old_alpha": FG_FAINT}.get(kind, FG_FAINT)
        stripe = tk.Frame(row.inner, bg=color, width=3, height=32)
        stripe.pack(side="left", fill="y", padx=(0, 10))

        box = tk.Frame(row.inner, bg=BG_ALT)
        box.pack(side="left", fill="both", expand=True)
        tk.Label(box, text=vid, bg=BG_ALT, fg=FG, anchor="w",
                 font=self.app.fonts["body"]).pack(fill="x")
        sub = f"{kind}"
        if meta.get("javaVersion"):
            sub += f"  ·  Java {meta['javaVersion']}"
        if not meta.get("has_jar"):
            sub += "  ·  缺少 jar"
        tk.Label(box, text=sub, bg=BG_ALT, fg=FG_FAINT, anchor="w",
                 font=self.app.fonts["small"]).pack(fill="x")

        row.attach()
        self._rows[vid] = row

    def _select(self, vid: str) -> None:
        self._selected = vid
        for k, row in self._rows.items():
            row.set_selected(k == vid)
        meta = version_meta(self.app.cfg.game_dir, vid)
        self._big_name.configure(text=vid)
        parts = [meta.get("type", "?")]
        if meta.get("javaVersion"):
            parts.append(f"Java {meta['javaVersion']}")
        if meta.get("jar_size"):
            parts.append(f"{meta['jar_size'] / 1024 / 1024:.0f} MB")
        if not meta.get("has_jar"):
            parts.append("⚠ 缺少 client.jar")
        self._big_sub.configure(text="   ·   ".join(parts))
        self._delete_btn.set_enabled(True)
        for btn in (self._world_btn, self._verify_btn, self._export_btn):
            btn.set_enabled(True)
        self._update_java_hint(vid)
        if self._mods_panel is not None:
            try:
                self._mods_panel.set_version(vid)
            except Exception:                        # noqa: BLE001
                pass
        # 反馈⑮：以前只有「模组」页签跟着走，下载页/浏览器还停在旧版本上，
        # 用户以为右侧面板没反应。现在把选中版本广播给所有关心它的页面。
        self.app.notify_version_selected(vid)

    # ------------------------------------------------------------ Java

    def _refresh_java(self) -> None:
        def work():
            game_dir = self.app.cfg.game_dir
            extra = self.app.cfg.get("java_path") or ""
            javas = detect_all(game_dir, extra)
            self.post(lambda: self._on_java_detected(javas))
        threading.Thread(target=work, daemon=True).start()

    def _on_java_detected(self, javas) -> None:
        self._javas = javas
        if not javas:
            self._java_label.configure(text="未检测到 Java，请在设置里手动指定", fg=DANGER)
            return
        if self._selected:
            self._update_java_hint(self._selected)
        else:
            best = javas[-1]
            self._java_label.configure(text=best.label, fg=FG_DIM)

    def _update_java_hint(self, vid: str) -> None:
        if not self._javas:
            return
        try:
            vjson = GameLauncher(self.app.cfg.game_dir).load_version(vid)
            need = required_java(vjson)
        except LaunchError:
            need = 8
        pick = pick_for_version(self._javas, need)
        if pick is None:
            self._java_label.configure(text=f"需要 Java {need}，但未找到", fg=DANGER)
            return
        ok = pick.major >= need
        text = f"{pick.label}   需要 Java {need}+"
        self._java_label.configure(text=text, fg=FG_DIM if ok else WARN)

    # ------------------------------------------------------------ 交互

    def _on_mem_change(self, value: int) -> None:
        try:
            self._mem_var.set(int(value))
        except tk.TclError:
            pass

    def _on_name_change(self, _e=None) -> None:
        if str(self._name_entry.cget("state")) == "disabled":
            return
        name = self._name_var.get().strip() or "Steve"
        self.app.cfg.set("username", name)
        self.app.cfg.save()
        self.app.refresh_account()

    def on_account_changed(self) -> None:
        """账号变了：正版 / 皮肤站账号锁住玩家名输入框，离线账号则回填它自己的名字。"""
        acc = self.app.current_account()
        if acc is not None and (acc.premium or acc.third_party):
            self._name_var.set(acc.name)
            self._name_entry.configure(state="disabled")
            self._acc_hint.configure(text="随账号", fg=ACCENT if acc.premium else FG_DIM)
            # 反馈⑥：名字由账号决定时，标签也说清楚，别让人以为还能自己改
            try:
                self._name_title.configure(text="账号名")
            except Exception:                        # noqa: BLE001
                pass
        elif acc is not None:
            self._name_entry.configure(state="normal")
            self._name_var.set(acc.name)
            self._acc_hint.configure(text="离线", fg=FG_FAINT)
            try:
                self._name_title.configure(text="玩家名")
            except Exception:                        # noqa: BLE001
                pass
        else:
            self._name_entry.configure(state="normal")
            self._name_var.set(self.app.cfg.get("username") or "Steve")
            self._acc_hint.configure(text="未登录", fg=FG_FAINT)
            try:
                self._name_title.configure(text="玩家名")
            except Exception:                        # noqa: BLE001
                pass
        # 右上角胶囊也一起刷新，避免两处显示不一致
        try:
            self.app.refresh_account()
        except Exception:                            # noqa: BLE001
            pass
        if self._accounts_panel is not None:
            try:
                self._accounts_panel.refresh()
            except Exception:                        # noqa: BLE001
                pass

    def _instance_dir(self) -> Path:
        """当前选中版本实际使用的游戏目录（考虑实例隔离）。"""
        from .. import instances, modpack
        game_dir = self.app.cfg.game_dir
        vid = self._selected
        if not vid:
            return game_dir
        sep = instances.effective(
            game_dir, vid,
            bool(self.app.cfg.get("separate_instances", False)) or modpack.is_pack(game_dir, vid))
        return instances.game_dir_for(game_dir, vid, sep)

    def _open_dir(self) -> None:
        from ..mods import open_folder
        d = self._instance_dir()
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        open_folder(d)

    def _open_logs(self) -> None:
        from ..mods import open_folder
        logs = self.app.cfg.game_dir / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        open_folder(logs)

    # ------------------------------------------------------ 工具：存档 / 校验 / 导出

    def handle_drop(self, paths) -> None:
        """在任何一页拖入文件都走这里：jar 装进当前实例的 mods，压缩包走整合包安装。"""
        jars, packs, other = [], [], []
        for path in paths:
            suffix = path.suffix.lower()
            if suffix == ".jar":
                jars.append(path)
            elif suffix in (".mrpack", ".zip"):
                packs.append(path)
            else:
                other.append(path)
        if jars:
            from ..mods import import_mods
            ok, errors = import_mods(self._instance_dir() / "mods", jars)
            if ok:
                self.app.notify(f"已导入 {ok} 个 Mod 到 {self._selected or '当前目录'}", "ok")
            if errors:
                messagebox.showwarning("部分未导入", "\n".join(errors[:10]), parent=self)
        if packs:
            from .pack_dialog import PackInstallDialog
            dlg = PackInstallDialog(self.app, packs[0],
                                    on_done=self._on_pack_installed,
                                    base_version=self._selected or "")
            try:
                dlg.grab_set()
            except tk.TclError:
                pass
        if other and not jars and not packs:
            self.app.notify("只支持拖入 .jar / .mrpack / .zip", "warn")

    def _on_pack_installed(self, vid: str) -> None:
        self.reload_versions()
        if vid:
            self._select(vid)
            self.app.notify(f"整合包已装成独立实例：{vid}", "ok")

    def _open_worlds(self) -> None:
        if not self._selected:
            return
        from .world_dialog import WorldDialog
        dlg = WorldDialog(self.app, self._instance_dir() / "saves", self._selected)
        dlg.grab_set()
        self.wait_window(dlg)

    def _open_verify(self) -> None:
        if not self._selected:
            return
        from .verify_dialog import VerifyDialog
        dlg = VerifyDialog(self.app, self._selected)
        dlg.grab_set()
        self.wait_window(dlg)

    def _export_pack(self) -> None:
        vid = self._selected
        if not vid:
            return
        from tkinter import filedialog
        default = f"{vid}.mrpack"
        target = filedialog.asksaveasfilename(
            parent=self, title="导出整合包", defaultextension=".mrpack",
            initialfile=default, initialdir=str(Path.home() / "Desktop"),
            filetypes=[("Modrinth 整合包", "*.mrpack"), ("所有文件", "*.*")])
        if not target:
            return
        from .. import exportpack

        self._log.write(f"开始导出整合包：{vid}")
        self.app.set_status("正在导出整合包…")
        game_dir = Path(self.app.cfg.game_dir)

        def work() -> None:
            try:
                res = exportpack.export_pack(
                    game_dir, vid, Path(target),
                    on_log=lambda m: self.post(lambda mm=m: self._log.write(mm)))
            except Exception as exc:                   # noqa: BLE001
                msg = str(exc)
                self.post(lambda: self.app.notify(f"导出失败：{msg}", "err"))
                self.post(lambda: self.app.set_status("就绪"))
                return
            text = res.summary()
            self.post(lambda: self._log.write(text))
            self.post(lambda: self.app.notify(text, "ok"))
            self.post(lambda: self.app.set_status("就绪"))

        import threading
        threading.Thread(target=work, daemon=True).start()


    def _delete_version(self) -> None:
        if not self._selected:
            return
        vid = self._selected
        if self._proc is not None and self._proc.poll() is None:
            self.app.notify("游戏正在运行，无法删除该版本", "warn")
            return
        if not messagebox.askyesno(
                "确认删除",
                f"确定要删除版本「{vid}」吗？\n\n"
                f"会删除整个 versions\\{vid} 目录（含 natives，存档不受影响）。",
                parent=self):
            return
        from ..installer import remove_version
        if remove_version(self.app.cfg.game_dir, vid):
            self.app.notify(f"已删除版本 {vid}", "ok")
            self._log.write(f"已删除版本 {vid}", "warn")
            self.reload_versions()
        else:
            messagebox.showerror("删除失败", f"无法删除 {vid}，可能有文件被占用",
                                 parent=self)

    def _stop_game(self) -> None:
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
                self._log.write("已发送结束信号", "warn")
            except OSError as exc:
                self._log.write(f"结束失败：{exc}", "err")
        self._stop_btn.set_enabled(False)
        self._stop_tail()

    def launch(self) -> None:
        if not self._selected:
            self.app.notify("请先选择一个版本", "warn")
            return
        if self._launching:
            return
        vid = self._selected
        self._on_name_change()
        self._launching = True
        self._launch_btn.set_enabled(False)
        threading.Thread(target=self._launch_work, args=(vid,), daemon=True).start()

    def _launch_work(self, vid: str) -> None:
        """整个启动流程放在后台线程：可能要下 Java / 下 authlib-injector。"""
        try:
            self._launch_flow(vid)
        except Exception as exc:                     # noqa: BLE001
            self._log.write(f"启动异常：{type(exc).__name__}: {exc}", "err")
            self._show_error(f"{type(exc).__name__}: {exc}")
        finally:
            self.post(self._launch_reset)

    def _launch_reset(self) -> None:
        self._launching = False
        try:
            self._launch_btn.set_enabled(self._proc is None or self._proc.poll() is not None)
        except (tk.TclError, AttributeError):
            pass

    def _show_error(self, msg: str) -> None:
        self.post(lambda: messagebox.showerror("启动失败", msg, parent=self))

    def _launch_flow(self, vid: str) -> None:
        game_dir = self.app.cfg.game_dir
        name = self._name_var.get().strip() or "Steve"

        # 有正版账号就用正版令牌，否则走离线（离线账号用自己的 UUID，保证皮肤/存档不串）
        account = self.app.ms_account
        skin = self.app.skin_account
        if account is not None:
            if account.expired:
                self._log.write("正版令牌已过期，正在续期…")
                try:
                    account = auth.refresh(account)
                    self.app.set_ms_account(account)
                except auth.AuthError as exc:
                    self._log.write(f"续期失败：{exc}", "err")
                    self._show_error(f"{exc}\n\n请到左侧账户处重新登录。")
                    return
            name = account.name
            uuid_str, token, user_type = account.uuid, account.access_token, "msa"
        elif skin is not None:
            name = skin.name or name
            uuid_str, token, user_type = skin.uuid, skin.access_token, "legacy"
        else:
            name, uuid_str, token, user_type = self.app.effective_account()

        try:
            launcher = GameLauncher(game_dir)
            vjson = launcher.load_version(vid)
        except LaunchError as exc:
            self._log.write(f"读取版本失败：{exc}", "err")
            self._show_error(str(exc))
            return

        need = required_java(vjson)
        java = pick_for_version(self._javas, need)
        if java is None and self.app.cfg.get("auto_java", True):
            self._log.write(f"本机没有 Java {need}+，自动下载中…")
            try:
                java = javaauto.find_or_install(
                    game_dir, need, detect_all(game_dir, self.app.cfg.get("java_path") or ""),
                    on_log=lambda m: self._log.write(m))
            except Exception as exc:                 # noqa: BLE001
                self._log.write(f"自动下载 Java 失败：{exc}", "err")
                java = None
            if java is not None:
                self._log.write(f"Java 已就绪：{java.path}")
                self.post(self._refresh_java)
        if java is None:
            self._show_error(f"没有可用的 Java（需要 {need}+）。\n"
                             f"可以到设置页点「立即下载」，或手动指定 java.exe。")
            return

        # 实例隔离（整合包、以及已经有 mods/存档的旧实例一律隔离）
        separate = instances.effective(
            game_dir, vid,
            bool(self.app.cfg.get("separate_instances", False)) or modpack.is_pack(game_dir, vid))
        inst = instances.game_dir_for(game_dir, vid, separate)
        if separate:
            instances.ensure_instance(inst)

        agents: list[str] = []
        if skin is not None:
            try:
                jar = skin_sites.download_injector(game_dir, on_log=lambda m: self._log.write(m))
                agents.append(skin_sites.javaagent(skin, jar))
                self._log.write(f"皮肤站注入：{skin.site_name}（{skin.api}）")
            except skin_sites.SkinError as exc:
                self._log.write(f"皮肤站注入失败，本次不带皮肤：{exc}", "warn")

        opts = LaunchOptions(
            version_id=vid,
            player_name=name,
            uuid=uuid_str,
            access_token=token,
            user_type=user_type,
            memory_mb=int(self._mem_var.get()),
            jvm_args=self.app.cfg.get("jvm_args") or "",
            instance_dir=inst if separate else None,
            javaagents=agents,
        )
        self.app.cfg.update(memory_mb=int(self._mem_var.get()))
        if account is None and skin is None:
            self.app.cfg.set("username", name)
            self.app.cfg.save()

        self._log.write(f"—— 启动 {vid} ——")
        self._log.write(f"Java: {java.path}")
        mode = "微软正版" if account is not None else ("皮肤站 " + skin.site_name if skin else "离线")
        self._log.write(f"内存: {opts.memory_mb} MB   玩家: {name}（{mode}）")
        self._log.write(f"游戏目录: {opts.instance_dir or game_dir}")

        try:
            cmd = launcher.build_command(vid, java, opts)
        except LaunchError as exc:
            self._log.write(f"构建命令行失败：{exc}", "err")
            self._show_error(str(exc))
            return
        except Exception as exc:                     # noqa: BLE001
            self._log.write(f"构建命令行异常：{type(exc).__name__}: {exc}", "err")
            self._show_error(f"{type(exc).__name__}: {exc}")
            return

        self._log.write("命令行：")
        self._log.write("  " + _quote_cmd(cmd))

        # 缺库检查
        missing = _missing_libs(launcher, vjson)
        if missing:
            self._log.write(f"警告：缺少 {len(missing)} 个库文件，游戏可能无法启动", "warn")
            for m in missing[:6]:
                self._log.write(f"    {m}", "warn")
            if len(missing) > 6:
                self._log.write(f"    …还有 {len(missing) - 6} 个", "warn")

        res = launcher.launch(vid, java, opts,
                              show_console=bool(self.app.cfg.get("show_console")))
        if not res.ok:
            self._log.write(f"启动失败：{res.error}", "err")
            self._show_error(res.error)
            return

        self.post(lambda: self._on_launched(vid, res))

    def _on_launched(self, vid: str, res) -> None:
        self._proc = res.process
        self._log.write(f"已启动，PID = {res.process.pid}", "ok")
        if res.log_path:
            self._log.write(f"日志：{res.log_path}")
        self._stop_btn.set_enabled(True)
        self.app.set_status(f"正在运行：{vid}", f"PID {res.process.pid}")

        if res.log_path:
            self._start_tail(res.log_path)

        def watch():
            try:
                code = res.process.wait()
            except Exception:                        # noqa: BLE001
                code = -1
            def done():
                self._log.write(f"游戏已退出，退出码 {code}",
                                "ok" if code == 0 else "warn")
                self.app.set_status("就绪")
                self._stop_btn.set_enabled(False)
                self._proc = None
                self._stop_tail()
                if code != 0:
                    self._diagnose(vid, res.log_path)
            self.post(done)
        threading.Thread(target=watch, daemon=True).start()

    # ------------------------------------------------------------ 崩溃诊断

    def _diagnose(self, vid: str, log_path=None) -> None:
        """游戏非正常退出时分析日志，把结论摆出来（不打断用户操作）。"""
        def work():
            try:
                diags, used = crash.analyze_game_dir(
                    self.app.cfg.game_dir, vid, log_path=log_path)
            except Exception:                        # noqa: BLE001
                diags, used = [], None
            self.post(lambda: self._show_diagnosis(vid, diags, used))
        threading.Thread(target=work, daemon=True).start()

    def _show_diagnosis(self, vid: str, diags, used) -> None:
        if not diags:
            self._log.write("没能在日志里认出明确原因，可以点「一键反馈」把日志打包发出去。", "warn")
            return
        self._log.write(f"诊断到 {len(diags)} 个可能原因：", "warn")
        for d in diags:
            self._log.write(f"  · {d.title}" + (f"（{d.detail}）" if d.detail else ""), "warn")
        from .crash_dialog import CrashDialog
        dlg = CrashDialog(self.app, vid, diags, used)
        try:
            dlg.grab_set()
        except tk.TclError:
            pass

    # ------------------------------------------------------------ 日志跟踪

    def _start_tail(self, path: Path) -> None:
        self._stop_tail()
        self._tail_stop = threading.Event()
        stop = self._tail_stop

        def work():
            offset = 0
            carry = ""
            while not stop.is_set():
                try:
                    size = path.stat().st_size
                except OSError:
                    size = 0
                if size > offset:
                    try:
                        with open(path, "r", encoding="utf-8", errors="replace") as fh:
                            fh.seek(offset)
                            chunk = fh.read()
                            offset = fh.tell()
                    except OSError:
                        chunk = ""
                    if chunk:
                        text = carry + chunk
                        parts = text.splitlines(keepends=True)
                        carry = ""
                        if parts and not parts[-1].endswith(("\n", "\r")):
                            carry = parts.pop()
                        for line in parts:
                            clean = _clean_log_line(line)
                            if clean:
                                self.post(lambda c=clean: self._log.write(c))
                stop.wait(0.6)

        threading.Thread(target=work, daemon=True).start()

    def _stop_tail(self) -> None:
        if self._tail_stop is not None:
            self._tail_stop.set()
            self._tail_stop = None


def _quote_cmd(cmd: list[str]) -> str:
    out = []
    for c in cmd:
        if not c or any(ch in c for ch in ' \t"'):
            out.append('"' + c.replace('"', '\\"') + '"')
        else:
            out.append(c)
    return " ".join(out)


_LOG_PREFIX = re.compile(r"^\[\d{2}:\d{2}:\d{2}\]\s*\[[^\]]*\]\s*:?\s*")


def _clean_log_line(line: str) -> str:
    """把 "[22:37:12] [Render thread/INFO]: xxx" 压成 "xxx"，并丢掉过于嘈杂的行。"""
    text = _LOG_PREFIX.sub("", line).rstrip()
    if not text or text.startswith("    at ") or text.startswith("\tat "):
        return ""
    return text


def _missing_libs(launcher: GameLauncher, vjson: dict) -> list[str]:
    from ..versionmeta import resolve_libraries
    missing = []
    for lib in resolve_libraries(vjson):
        p = launcher.libraries_dir / Path(lib.path)
        if not p.is_file() and not lib.is_native:
            missing.append(lib.path)
    return missing
