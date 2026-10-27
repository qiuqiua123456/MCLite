"""设置页：游戏目录、Java、内存、下载源、账户、关于。"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .. import APP_NAME, __version__
from ..java import detect_all
from ..mods import open_folder
from . import responsive
from .theme import (
    ACCENT, BG, BG_ALT, BG_HOVER, BORDER, DANGER, FG, FG_DIM, FG_FAINT,
    SUCCESS, THEME, THEMES, THEME_ORDER, WARN, FlatButton, ScrollFrame, Slider,
)
from .widgets import LogPanel, Page


def _label(parent, text: str, w: int = 12, pack: bool = True):
    lbl = tk.Label(parent, text=text, bg=BG, fg=FG_DIM, width=w, anchor="w",
                   font=("Microsoft YaHei UI", 9))
    if pack:
        lbl.pack(side="left")
    return lbl


def _hint(parent, text: str):
    lbl = tk.Label(parent, text=text, bg=BG, fg=FG_FAINT,
                   font=("Microsoft YaHei UI", 8))
    lbl.pack(side="left", padx=(10, 0))
    return lbl


def _entry(parent, textvariable, width: int = 40):
    e = tk.Entry(parent, textvariable=textvariable, bg=BG_ALT, fg=FG,
                 insertbackground=FG, bd=0, highlightthickness=1,
                 highlightbackground=BORDER, highlightcolor=ACCENT,
                 font=("Microsoft YaHei UI", 9), width=width)
    return e


class SettingsPage(Page):
    title = "设置"

    def build(self) -> None:
        self._javas = []
        root = tk.Frame(self, bg=BG)
        root.pack(fill="both", expand=True, padx=24, pady=(20, 12))

        head = tk.Frame(root, bg=BG)
        head.pack(fill="x")
        tk.Label(head, text="设置", bg=BG, fg=FG, font=self.app.fonts["h1"]).pack(side="left")
        FlatButton(head, "保存设置", command=self.save_all, kind="primary",
                   height=32, width=100, bg=BG).pack(side="right", pady=4)

        scroll = ScrollFrame(root, bg=BG)
        scroll.pack(fill="both", expand=True, pady=(14, 0))
        box = scroll.inner

        # ------------------------------------------------ 游戏
        self._section(box, "游戏")
        r = self._row(box)
        _label(r, "游戏目录")
        self._dir_var = tk.StringVar(value=str(self.app.cfg.game_dir))
        _entry(r, self._dir_var, 20).pack(side="left", fill="x", expand=True, ipady=5)
        FlatButton(r, "浏览", command=self._browse_dir, kind="normal", height=28,
                   width=60, bg=BG).pack(side="left", padx=(8, 0))
        FlatButton(r, "打开", command=lambda: open_folder(Path(self._dir_var.get())),
                   kind="ghost", height=28, width=56, bg=BG).pack(side="left", padx=(6, 0))

        r = self._row(box)
        _label(r, "最近目录")
        self._recent_var = tk.StringVar(value="")
        self._recent_box = ttk.Combobox(r, textvariable=self._recent_var, state="readonly",
                                        width=24, font=self.app.fonts["body"])
        self._recent_box.pack(side="left", fill="x", expand=True, ipady=3)
        self._recent_box.bind("<<ComboboxSelected>>", self._on_recent)
        FlatButton(r, "移除", command=self._forget_recent, kind="ghost", height=28,
                   width=56, bg=BG).pack(side="left", padx=(8, 0))
        self._sync_recent()

        r = self._row(box)
        _label(r, "玩家名")
        self._name_var = tk.StringVar(value=self.app.cfg.get("username") or "Steve")
        _entry(r, self._name_var, 24).pack(side="left", ipady=5)
        _hint(r, "离线登录使用，正式服请使用正版账号")

        r = self._row(box)
        _label(r, "内存 (MB)")
        self._mem_var = tk.IntVar(value=int(self.app.cfg.get("memory_mb") or 4096))
        self._mem_slider = Slider(r, 1024, 32768, self._mem_var.get(), step=512,
                                  command=lambda v: self._mem_var.set(v),
                                  width=240, suffix=" MB", bg=BG)
        self._mem_slider.pack(side="left")
        _hint(r, "建议 4096；大型整合包可上 8192")

        r = self._row(box)
        _label(r, "窗口尺寸")
        self._w_var = tk.StringVar(value=str(self.app.cfg.get("window_width") or 900))
        self._h_var = tk.StringVar(value=str(self.app.cfg.get("window_height") or 560))
        _entry(r, self._w_var, 8).pack(side="left", ipady=5)
        tk.Label(r, text="×", bg=BG, fg=FG_DIM).pack(side="left", padx=6)
        _entry(r, self._h_var, 8).pack(side="left", ipady=5)
        FlatButton(r, "全屏启动", command=self._toggle_fullscreen, kind="ghost",
                   height=28, width=84, bg=BG).pack(side="left", padx=(14, 0))

        r = self._row(box)
        _label(r, "实例")
        self._separate_var = tk.BooleanVar(value=bool(self.app.cfg.get("separate_instances", True)))
        tk.Checkbutton(r, text="版本隔离（每个版本独立的 mods / 存档 / 配置）",
                       variable=self._separate_var, bg=BG, fg=FG, selectcolor=BG_ALT,
                       activebackground=BG, activeforeground=FG, bd=0,
                       highlightthickness=0,
                       font=("Microsoft YaHei UI", 9)).pack(side="left")
        _hint(r, "整合包始终隔离")

        # ------------------------------------------------ Java
        self._section(box, "Java 运行时")
        r = self._row(box)
        _label(r, "Java 路径")
        self._java_var = tk.StringVar(value=self.app.cfg.get("java_path") or "")
        _entry(r, self._java_var, 20).pack(side="left", fill="x", expand=True, ipady=5)
        FlatButton(r, "浏览", command=self._browse_java, kind="normal", height=28,
                   width=60, bg=BG).pack(side="left", padx=(8, 0))
        FlatButton(r, "检测", command=self.detect_java, kind="normal", height=28,
                   width=60, bg=BG).pack(side="left", padx=(6, 0))

        r = self._row(box, pady=(2, 8))
        self._java_list = tk.Label(r, text="正在检测…", bg=BG, fg=FG_DIM,
                                   anchor="w", justify="left",
                                   font=("Consolas", 8))
        self._java_list.pack(side="left", fill="x")

        r = self._row(box)
        _label(r, "自动下载")
        self._auto_java_var = tk.BooleanVar(value=bool(self.app.cfg.get("auto_java", True)))
        tk.Checkbutton(r, text="启动时自动下载缺失的 Java", variable=self._auto_java_var,
                       bg=BG, fg=FG, selectcolor=BG_ALT, activebackground=BG,
                       activeforeground=FG, bd=0, highlightthickness=0,
                       font=("Microsoft YaHei UI", 9)).pack(side="left")
        self._jdk_major = tk.StringVar(value="17")
        tk.Label(r, text="版本", bg=BG, fg=FG_FAINT,
                 font=("Microsoft YaHei UI", 8)).pack(side="left", padx=(14, 4))
        tk.Entry(r, textvariable=self._jdk_major, width=4, bg=BG_ALT, fg=FG,
                 insertbackground=FG, bd=0, highlightthickness=1,
                 highlightbackground=BORDER, highlightcolor=ACCENT,
                 font=("Microsoft YaHei UI", 9)).pack(side="left", ipady=3)
        self._jdk_btn = FlatButton(r, "立即下载", command=self._download_java,
                                   kind="primary", height=26, width=84,
                                   font=("Microsoft YaHei UI", 8), bg=BG)
        self._jdk_btn.pack(side="left", padx=(6, 0))
        self._jdk_hint = _hint(r, "从 Mojang 官方源下载到 runtime 目录")

        # ------------------------------------------------ 下载
        self._section(box, "下载")
        r = self._row(box)
        _label(r, "下载源")
        self._source_var = tk.StringVar(value=self.app.cfg.get("download_source") or "official")
        for value, text in (("official", "Mojang 官方"), ("bmclapi", "BMCLAPI 镜像")):
            tk.Radiobutton(r, text=text, variable=self._source_var, value=value,
                           bg=BG, fg=FG, selectcolor=BG_ALT, activebackground=BG,
                           activeforeground=FG, bd=0, highlightthickness=0,
                           font=("Microsoft YaHei UI", 9)).pack(side="left", padx=(0, 14))

        r = self._row(box)
        _label(r, "下载线程")
        self._threads_var = tk.IntVar(value=int(self.app.cfg.get("download_threads") or 16))
        self._threads_slider = Slider(r, 1, 32, self._threads_var.get(), step=1,
                                      command=lambda v: self._threads_var.set(v),
                                      width=200, bg=BG)
        self._threads_slider.pack(side="left")
        _hint(r, "线程越多越快，但占用也越高")

        # ------------------------------------------------ 账户
        self._section(box, "账户")
        r = self._row(box)
        _label(r, "当前账户")
        self._acc_label = tk.Label(r, text="", bg=BG, fg=FG,
                                   font=self.app.fonts["body"], anchor="w")
        self._acc_label.pack(side="left", padx=(0, 12))
        FlatButton(r, "账号管理", command=self._open_accounts, kind="normal",
                   height=34, width=104, font=self.app.fonts["small"],
                   bg=BG).pack(side="left", padx=(0, 8))

        r = self._row(box)
        _label(r, "登录")
        self._login_row = responsive.FlowRow(r, gap=8, row_gap=8, bg=BG)
        self._login_row.pack(side="left", fill="x", expand=True)
        self._login_btns = [
            FlatButton(self._login_row, "微软正版登录", command=self.app.open_login,
                       kind="normal", height=34, width=126,
                       font=self.app.fonts["small"], bg=BG),
            FlatButton(self._login_row, "第三方皮肤站登录",
                       command=self.app.open_skin_login,
                       kind="normal", height=34, width=150,
                       font=self.app.fonts["small"], bg=BG),
            FlatButton(self._login_row, "皮肤管理", command=self.app.open_skin_manager,
                       kind="normal", height=34, width=104,
                       font=self.app.fonts["small"], bg=BG),
        ]
        self._login_row.add_all(*self._login_btns)
        self._login_hint = _hint(r, "支持 LittleSkin / MUA / Blessing Skin / 自定义")

        # ------------------------------------------------ 界面
        self._section(box, "界面")
        r = self._row(box)
        _label(r, "主题配色")
        # 主题按钮一行 4 个；窄窗口（880x560 实测 box 宽 587、这排要 590）会被
        # 压掉 3px，最后一个按钮的圆角就贴边了。FlowRow 放不下自动换行。
        self._theme_row = responsive.FlowRow(r, gap=8, row_gap=6, bg=BG)
        self._theme_row.pack(side="left", fill="x", expand=True)
        self._theme_btns: dict[str, FlatButton] = {}
        for key in THEME_ORDER:
            label = THEMES[key].get("label", key)
            # 选中的用 accent_soft（淡主色填充）：亮色主题下不会变成一块深蓝色
            btn = FlatButton(self._theme_row, label,
                             command=lambda k=key: self._set_theme(k),
                             kind="accent_soft" if key == THEME else "normal",
                             height=28, width=92, font=("Microsoft YaHei UI", 8), bg=BG)
            self._theme_row.add(btn)
            self._theme_btns[key] = btn

        # ------------------------------------------------ 启动参数
        self._section(box, "启动参数")
        r = self._row(box)
        _label(r, "附加 JVM 参数")
        self._jvm_var = tk.StringVar(value=self.app.cfg.get("jvm_args") or "")
        _entry(r, self._jvm_var, 20).pack(side="left", fill="x", expand=True, ipady=5)

        r = self._row(box)
        _label(r, "杂项")
        self._console_var = tk.BooleanVar(value=bool(self.app.cfg.get("show_console")))
        tk.Checkbutton(r, text="显示游戏控制台窗口", variable=self._console_var,
                       bg=BG, fg=FG, selectcolor=BG_ALT, activebackground=BG,
                       activeforeground=FG, bd=0, highlightthickness=0,
                       font=("Microsoft YaHei UI", 9)).pack(side="left")
        FlatButton(r, "打开日志目录", command=self._open_logs, kind="ghost",
                   height=26, width=100, font=("Microsoft YaHei UI", 8),
                   bg=BG).pack(side="left", padx=(16, 0))
        FlatButton(r, "一键反馈（打包日志）", command=self._feedback, kind="ghost",
                   height=26, width=132, font=("Microsoft YaHei UI", 8),
                   bg=BG).pack(side="left", padx=(8, 0))

        # ------------------------------------------------ 关于
        self._section(box, "关于")
        info = tk.Frame(box, bg=BG_ALT)
        info.pack(fill="x", pady=(0, 16))
        ipad = tk.Frame(info, bg=BG_ALT, padx=16, pady=14)
        ipad.pack(fill="x")
        tk.Label(ipad, text=f"{APP_NAME}  v{__version__}", bg=BG_ALT, fg=FG,
                 font=("Segoe UI", 12, "bold"), anchor="w").pack(fill="x")
        tk.Label(ipad, text="一个用 Python + tkinter 写的轻量 Minecraft 启动器。\n"
                            "支持原版版本下载安装、离线启动、Mod 管理与本地实例管理。",
                 bg=BG_ALT, fg=FG_DIM, anchor="w", justify="left",
                 font=("Microsoft YaHei UI", 9)).pack(fill="x", pady=(6, 0))
        tk.Label(ipad, text=f"配置文件：{self.app.cfg.path}", bg=BG_ALT, fg=FG_FAINT,
                 anchor="w", font=("Consolas", 8)).pack(fill="x", pady=(8, 0))

        self._after(250, self.detect_java)

    # ------------------------------------------------------------ 自适应宽度

    def _after(self, delay: int, fn) -> None:
        try:
            self.after(delay, fn)
        except tk.TclError:
            pass

    def on_resize(self, width: int) -> None:
        """按页面宽度收窄按钮行、给长提示换行。

        用户反馈「在往小调整窗口的时候自动调整分辨率使按键能够完整显示」：
        设置页原来有多行 4 个按钮横排（登录行 126+150+104）、多行长提示不换行，
        882x560 时被压 7 个控件，最狠的一行想要 736 只有 589。
        """
        if width <= 1:
            return
        box_w = max(200, width - 48 - 24)
        login = getattr(self, "_login_row", None)
        if login is not None:
            try:
                login.reflow(box_w - 90)
            except tk.TclError:
                pass
        theme_row = getattr(self, "_theme_row", None)
        if theme_row is not None:
            # 主题按钮前面还有 12 字符宽的标签（约 90px）
            try:
                theme_row.reflow(box_w - 90)
            except tk.TclError:
                pass
        # 长提示（「从 Mojang 官方源下载到 runtime 目录」等）改成换行，不再撑破行
        try:
            responsive.wrap_labels(self, box_w)
        except tk.TclError:
            pass
        # 同一行里被兄弟控件挤窄的提示语（按实测宽度换行）。
        # ⚠ 不能只跑一次：改 wraplength 本身会改变布局，第一次量到的宽度往往
        # 还是旧的（实测 after(120) 时 _jdk_hint 还是 199 宽、够放，等布局稳定
        # 后才被挤到 150）。所以排三次，几何一稳定就会被抓住。
        for delay in (60, 200, 500):
            try:
                self.after(delay, lambda: responsive.fix_clipped(self))
            except tk.TclError:
                break

    # ------------------------------------------------------------ 布局助手

    def _section(self, parent, title: str) -> None:
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(14, 6))
        tk.Label(row, text=title, bg=BG, fg=ACCENT,
                 font=("Microsoft YaHei UI", 10, "bold")).pack(side="left")
        tk.Frame(row, bg=BORDER, height=1).pack(side="left", fill="x", expand=True,
                                                padx=(10, 0), pady=(8, 0))

    def _row(self, parent, pady=(4, 4)) -> tk.Frame:
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=pady)
        return row

    # ------------------------------------------------------------ 动作

    def _open_accounts(self) -> None:
        self.app.open_accounts()
        self.after(120, self._refresh_account)

    def _refresh_account(self) -> None:
        """把当前账号显示到「账户」区，账号切换后同步。"""
        try:
            acc = self.app.current_account()
        except Exception:                              # noqa: BLE001
            acc = None
        if acc is None:
            text, color = "未设置（启动时按玩家名离线登录）", FG_DIM
        else:
            kind = {"msa": "正版", "yggdrasil": "皮肤站", "offline": "离线"}.get(acc.kind, acc.kind)
            text = f"{acc.name}　·　{acc.label or kind}"
            color = ACCENT if acc.premium or acc.third_party else FG
        self._acc_label.configure(text=text, fg=color)

    def on_show(self) -> None:
        self._refresh_account()

    def _browse_dir(self) -> None:
        d = filedialog.askdirectory(parent=self, title="选择 .minecraft 游戏目录",
                                    initialdir=self._dir_var.get() or str(Path.home()))
        if d:
            self._apply_dir(d)

    def _apply_dir(self, path: str) -> None:
        """选中目录后**立刻生效**，不用再点「保存设置」。

        用户反馈「游戏目录选择无效」：原来只改输入框里的字，配置要等点保存
        才落盘，而首页/下载页各自缓存着旧的 cfg.game_dir，看起来就像没换。
        """
        path = str(path or "").strip()
        if not path:
            return
        self._dir_var.set(path)
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        self.app.cfg.update(game_dir=path)
        self.app.cfg.save()
        self._remember_dir(path, save=False)
        self._sync_recent()
        self._refresh_after_dir_change()
        self.app.notify(f"游戏目录已切换到 {path}", "ok")

    def _refresh_after_dir_change(self) -> None:
        """让所有缓存了游戏目录的界面重新读一遍。"""
        home = self.app._pages.get("home")
        if home is not None:
            try:
                home.on_show()
                home.reload_versions()
            except Exception:                        # noqa: BLE001
                pass
        inst = self.app._pages.get("install")
        if inst is not None:
            try:
                inst.on_show()
            except Exception:                        # noqa: BLE001
                pass

    # ------------------------------------------------------------ 多游戏目录

    def _recent_dirs(self) -> list[str]:
        items = self.app.cfg.get("recent_dirs") or []
        return [str(x) for x in items if str(x).strip()]

    def _remember_dir(self, path: str, save: bool = True) -> None:
        path = str(path or "").strip()
        if not path:
            return
        items = [p for p in self._recent_dirs() if p.lower() != path.lower()]
        items.insert(0, path)
        self.app.cfg.update(recent_dirs=items[:8])
        if save:
            self.app.cfg.save()
        self._sync_recent()

    def _sync_recent(self) -> None:
        box = getattr(self, "_recent_box", None)
        if box is None:
            return
        items = self._recent_dirs()
        current = self._dir_var.get().strip()
        if current and current not in items:
            items = [current] + items
        box.configure(values=items)
        self._recent_var.set(items[0] if items else "")

    def _on_recent(self, _e=None) -> None:
        path = self._recent_var.get()
        if path:
            self._apply_dir(path)

    def _forget_recent(self) -> None:
        path = self._recent_var.get()
        if not path:
            return
        items = [p for p in self._recent_dirs() if p != path]
        self.app.cfg.update(recent_dirs=items)
        self.app.cfg.save()
        self._sync_recent()

    def _browse_java(self) -> None:
        f = filedialog.askopenfilename(
            parent=self, title="选择 java.exe",
            filetypes=[("Java 可执行文件", "java.exe javaw.exe"), ("所有文件", "*.*")])
        if f:
            self._java_var.set(f)
            self.detect_java()

    def _toggle_fullscreen(self) -> None:
        cur = bool(self.app.cfg.get("fullscreen"))
        self.app.cfg.set("fullscreen", not cur)
        self.app.notify("全屏启动：" + ("开" if not cur else "关"), "ok")

    def _open_logs(self) -> None:
        from ..mods import open_folder
        logs = Path(self._dir_var.get().strip() or ".") / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        open_folder(logs)

    def _feedback(self) -> None:
        """把日志、崩溃报告、模组清单和系统信息打成一个 zip 放桌面。"""
        import threading

        from .. import feedback
        from ..java import detect_all

        self.app.notify("正在打包反馈信息…", "info")
        game_dir = self._dir_var.get().strip() or self.app.cfg.game_dir

        def work():
            try:
                javas = detect_all(game_dir, self._java_var.get())
            except Exception:                        # noqa: BLE001
                javas = []
            try:
                path = feedback.collect(self.app.cfg, javas, game_dir=game_dir)
            except Exception as exc:                 # noqa: BLE001
                self.app.post(lambda: self.app.notify(f"打包失败：{exc}", "err"))
                return
            self.app.post(lambda: self.app.notify(f"反馈包已保存到桌面：{path.name}", "ok"))

        threading.Thread(target=work, daemon=True).start()

    def detect_java(self) -> None:
        self._java_list.configure(text="正在检测…", fg=FG_DIM)
        extra = self._java_var.get()
        game_dir = Path(self._dir_var.get())

        def work():
            javas = detect_all(game_dir, extra)
            self.post(lambda: self._on_java(javas))

        threading.Thread(target=work, daemon=True).start()

    def _on_java(self, javas) -> None:
        self._javas = javas
        if not javas:
            self._java_list.configure(
                text="未检测到 Java。请安装 JRE/JDK（1.20 需要 Java 17+），或在上方手动指定 java.exe",
                fg=DANGER)
            return
        lines = []
        for j in javas:
            mark = "  ← 已指定" if self._java_var.get() and str(j.path).lower() == self._java_var.get().lower() else ""
            lines.append(f"Java {j.major:<2} {j.bits}位  {j.version:<10} {j.path}{mark}")
        self._java_list.configure(text="\n".join(lines[:8]), fg=FG_DIM)

    # ------------------------------------------------------------ 主题 / Java 下载

    def _set_theme(self, key: str) -> None:
        """换主题：运行时直接生效（App 会就地重建界面，不重启进程）。"""
        from . import theme as theme_mod

        if key == theme_mod.THEME:
            self.app.notify("已经是这个配色了", "info")
            return
        name = theme_mod.theme_label(key)
        self.app.apply_theme(key)
        self.app.notify(f"已切换到「{name}」配色", "ok")

    def _download_java(self) -> None:
        from .. import javaauto

        try:
            major = int(str(self._jdk_major.get()).strip())
        except ValueError:
            messagebox.showerror("版本不对", "Java 版本号请填数字，例如 17", parent=self)
            return
        game_dir = Path(self._dir_var.get().strip() or self.app.cfg.game_dir)
        self._jdk_btn.set_enabled(False)
        self._jdk_hint.configure(text=f"正在准备 Java {major}…", fg=FG_DIM)

        def log(msg: str) -> None:
            self.post(lambda: self._jdk_hint.configure(text=msg[:70], fg=FG_DIM))

        def work():
            try:
                info = javaauto.install_java(game_dir, major, on_log=log)
            except Exception as exc:                 # noqa: BLE001
                self.post(lambda: self._java_failed(str(exc)))
                return
            self.post(lambda: self._java_done(info))

        threading.Thread(target=work, daemon=True).start()

    def _java_failed(self, msg: str) -> None:
        self._jdk_btn.set_enabled(True)
        self._jdk_hint.configure(text="下载失败：" + msg[:60], fg=DANGER)
        self.app.notify("Java 下载失败", "err")

    def _java_done(self, info) -> None:
        self._jdk_btn.set_enabled(True)
        self._jdk_hint.configure(text=f"已就绪：Java {info.major}  {info.version}", fg=SUCCESS)
        self.app.notify(f"Java {info.major} 下载完成", "ok")
        self.detect_java()

    # ------------------------------------------------------------ 保存

    def save_all(self) -> None:
        game_dir = self._dir_var.get().strip()
        if not game_dir:
            messagebox.showerror("保存失败", "游戏目录不能为空", parent=self)
            return
        try:
            Path(game_dir).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("保存失败", f"无法创建目录：{exc}", parent=self)
            return

        try:
            width = int(self._w_var.get())
            height = int(self._h_var.get())
        except ValueError:
            width, height = 900, 560

        self.app.cfg.update(
            game_dir=game_dir,
            username=(self._name_var.get().strip() or "Steve"),
            memory_mb=int(self._mem_var.get()),
            java_path=self._java_var.get().strip(),
            download_source=self._source_var.get(),
            download_threads=int(self._threads_var.get()),
            jvm_args=self._jvm_var.get().strip(),
            window_width=width,
            window_height=height,
            fullscreen=bool(self.app.cfg.get("fullscreen")),
            show_console=bool(self._console_var.get()),
            separate_instances=bool(self._separate_var.get()),
            auto_java=bool(self._auto_java_var.get()),
        )
        self._remember_dir(game_dir)
        self.app.refresh_account()
        self.app.notify("设置已保存", "ok")

        home = self.app._pages.get("home")
        if home is not None:
            home.reload_versions()
            home._refresh_java()
            panel = getattr(home, "_mods_panel", None)
            if panel is not None:
                try:
                    panel.refresh()
                except Exception:                    # noqa: BLE001
                    pass
        self.app.set_status("设置已保存")
