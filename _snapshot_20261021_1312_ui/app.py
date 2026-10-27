"""主窗口：顶部蓝色标题栏（品牌 + 居中导航 + 账户） + 页面容器 + 底部状态栏。"""

from __future__ import annotations

import queue
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont
from tkinter import messagebox, ttk

from .. import APP_NAME, __version__, accounts
from ..config import Config
from ..ui.theme import (
    ACCENT, ACCENT_DARK, ACCENT_HOVER, BG, BG_ALT, BG_HOVER, BORDER, DANGER, FG,
    FG_DIM, FG_FAINT, SUCCESS, WARN, FlatButton, apply_style, gradient, mix, round_rect,
)
from .widgets import Avatar, Toast

# 拖拽支持：tkinterdnd2 是可选的，缺了也不影响启动。
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    _DND_WRAPPER = TkinterDnD.DnDWrapper
except Exception:                                     # noqa: BLE001
    DND_FILES = None
    TkinterDnD = None
    _DND_WRAPPER = None

_BASES = (tk.Tk,) if _DND_WRAPPER is None else (tk.Tk, _DND_WRAPPER)

NAV_ITEMS = [
    ("home",    "开始",  "\u25b6"),
    ("install", "下载",  "\u2b07"),
    ("mods",    "Mod",   "\u2699"),
    ("settings","设置",  "\u2692"),
]


class NavProxy:
    """``show_page`` 用的轻量代理：导航的真实绘制在 TopBar 上。"""

    def __init__(self, bar: "TopBar", key: str):
        self._bar = bar
        self.key = key

    def set_active(self, value: bool) -> None:
        if value:
            self._bar.set_active_key(self.key)


class TopBar(tk.Canvas):
    """PCL 风格顶栏：蓝色横向渐变 + 左侧品牌 + 居中导航胶囊 + 右侧账户胶囊。"""

    H = 54

    def __init__(self, master, app):
        super().__init__(master, height=self.H, highlightthickness=0, bd=0,
                         bg=ACCENT_DARK)
        self.app = app
        self._bar_w = 1040
        self._active = ""
        self._hover = ""
        self._name = ""
        self._sub = ""
        self._nav_hits: list[tuple[str, float, float]] = []
        self._acc_hit: tuple[float, float] = (0, 0)

        self._f_nav = tkfont.Font(family="Microsoft YaHei UI", size=10)
        self._f_nav_b = tkfont.Font(family="Microsoft YaHei UI", size=10, weight="bold")
        self._f_brand = tkfont.Font(family="Segoe UI", size=12, weight="bold")
        self._f_small = tkfont.Font(family="Segoe UI", size=8)
        self._f_logo = tkfont.Font(family="Segoe UI", size=15, weight="bold")

        self.avatar = Avatar(self, size=30, bg=mix(ACCENT_HOVER, "#FFFFFF", 0.14))
        self.bind("<Configure>", self._on_configure)
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", lambda _e: self._set_hover(""))
        self.bind("<Button-1>", self._on_click)
        self._draw()

    # ---------------------------------------------------------- 事件

    def _on_configure(self, event) -> None:
        if event.width > 100 and event.width != self._bar_w:
            self._bar_w = event.width
            self._draw()

    def _hit(self, x: float, y: float) -> str:
        if not (0 <= y <= self.H):
            return ""
        for key, x0, x1 in self._nav_hits:
            if x0 <= x <= x1:
                return key
        return ""

    def _on_motion(self, event) -> None:
        key = self._hit(event.x, event.y)
        if key != self._hover:
            self._hover = key
            self.configure(cursor="hand2" if key else "")
            self._draw()

    def _on_click(self, event) -> None:
        key = self._hit(event.x, event.y)
        if key:
            self.app.show_page(key)
            return
        x0, x1 = self._acc_hit
        if x0 <= event.x <= x1:
            self.app.open_accounts()

    def _set_hover(self, key: str) -> None:
        if key != self._hover:
            self._hover = key
            self._draw()

    # ---------------------------------------------------------- 接口

    def set_active_key(self, key: str) -> None:
        self._active = key
        self._draw()

    def set_account(self, name: str, sub: str, premium: bool = False) -> None:
        self._name = name or ""
        self._sub = sub or ""
        self._premium = premium
        self.avatar.draw_letter(self._name or "?")
        self._draw()

    # ---------------------------------------------------------- 绘制

    def _draw(self) -> None:
        self.delete("all")
        w, h = self._bar_w, self.H
        gradient(self, w, h, ACCENT_DARK, ACCENT_HOVER, steps=160, tag="topbg")
        # 底边一条白色高光线，让顶栏和内容区分开
        self.create_line(0, h - 1, w, h - 1, fill=mix(ACCENT_DARK, "#000000", 0.18), width=1)

        # ---- 品牌
        cy = h / 2
        round_rect(self, 16, cy - 15, 46, cy + 15, 9, fill="#FFFFFF", outline="#FFFFFF")
        self.create_text(31, cy, text="M", fill=ACCENT_DARK, font=self._f_logo)
        self.create_text(54, cy - 7, text=APP_NAME, anchor="w", fill="#FFFFFF",
                         font=self._f_brand)
        self.create_text(54, cy + 9, text=f"v{__version__}", anchor="w",
                         fill=mix("#FFFFFF", ACCENT_DARK, 0.30), font=self._f_small)

        # ---- 居中导航
        self._nav_hits = []
        widths: list[float] = []
        for _key, text, _icon in NAV_ITEMS:
            widths.append(max(76.0, self._f_nav_b.measure(text) + 44.0))
        gap = 6.0
        total = sum(widths) + gap * (len(widths) - 1)
        x = (w - total) / 2
        for (key, text, _icon), pw in zip(NAV_ITEMS, widths):
            active = key == self._active
            hover = key == self._hover and not active
            if active:
                fill, fg = "#FFFFFF", ACCENT_DARK
            elif hover:
                fill, fg = mix(ACCENT_HOVER, "#FFFFFF", 0.20), "#FFFFFF"
            else:
                fill, fg = "", "#D6E6FA"
            if fill:
                round_rect(self, x, cy - 16, x + pw, cy + 16, 16, fill=fill, outline=fill)
            self.create_text(x + pw / 2, cy, text=text, fill=fg,
                             font=self._f_nav_b if active else self._f_nav)
            self._nav_hits.append((key, x, x + pw))
            x += pw + gap

        # ---- 右侧账户胶囊
        chip_fill = mix(ACCENT_HOVER, "#FFFFFF", 0.14)
        name_w = float(self._f_nav_b.measure(self._name or "Steve"))
        chip_w = 12 + 30 + 9 + name_w + 26
        x1 = w - 14
        x0 = x1 - chip_w
        self._acc_hit = (x0, x1)
        if x0 > 0:
            round_rect(self, x0, cy - 16, x1, cy + 16, 16, fill=chip_fill, outline=chip_fill)
            self.avatar.configure(bg=chip_fill)
            self.create_window(x0 + 11, cy, window=self.avatar, anchor="w")
            self.create_text(x0 + 11 + 38, cy, text=self._name or "Steve", anchor="w",
                             fill="#FFFFFF", font=self._f_nav_b)
            self.create_text(x1 - 13, cy, text="\u25be", fill=mix("#FFFFFF", ACCENT_DARK, 0.25),
                             font=self._f_small)


class App(*_BASES):
    def __init__(self) -> None:
        super().__init__()
        self.cfg = Config()
        self.fonts = apply_style(self)
        self._accounts = accounts.load(self.cfg)
        if not self._accounts and self.cfg.get("username"):
            self._accounts = [accounts.Account.new_offline(str(self.cfg.get("username")))]
            self.cfg.set("current_account", 0)

        self._dnd_ok = False
        if _DND_WRAPPER is not None:
            try:
                TkinterDnD._require(self)
                self._dnd_ok = True
            except Exception:                         # noqa: BLE001
                self._dnd_ok = False

        self.title(f"{APP_NAME}  {__version__}")
        self.geometry("1160x724")
        self._set_icon()
        self.minsize(880, 560)
        self.configure(bg=BG)
        self._center()

        try:
            self.iconbitmap(default="")
        except tk.TclError:
            pass

        self._pages: dict[str, tk.Frame] = {}
        self._nav: dict[str, NavButton] = {}
        self._current = ""
        self._running_task = False
        self._main_queue: queue.Queue = queue.Queue()

        self._build()
        self.show_page("home")
        self._drain_queue()

    # ------------------------------------------------------------ 跨线程
    def post(self, fn) -> None:
        """从任意线程把回调排到主线程。"""
        self._main_queue.put(fn)

    def _drain_queue(self) -> None:
        for _ in range(64):
            try:
                fn = self._main_queue.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception:                        # noqa: BLE001
                pass
        try:
            self.after(40, self._drain_queue)
        except tk.TclError:
            pass

    # ------------------------------------------------------------ 布局

    def _center(self) -> None:
        self.update_idletasks()
        w, h = 1160, 724
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2 - 20)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build(self) -> None:
        # 换主题后就地重建，ttk 样式与字体得跟着当前颜色重新生成
        self.fonts = apply_style(self)
        self.configure(bg=BG)

        # ---------------- 顶部蓝色渐变栏
        self._topbar = TopBar(self, self)
        self._topbar.pack(side="top", fill="x")

        body = tk.Frame(self, bg=BG)
        body.pack(side="top", fill="both", expand=True)

        # ---------------- 左侧：账户卡 + 快捷入口
        self._side = tk.Frame(body, bg=BG_ALT, width=248)
        self._side.pack(side="left", fill="y")
        self._side.pack_propagate(False)
        tk.Frame(body, bg=BORDER, width=1).pack(side="left", fill="y")

        self._account_frame = tk.Frame(self._side, bg=BG_ALT)
        self._account_frame.pack(fill="x", pady=(18, 0), padx=16)
        self._build_account()

        # ---------------- 右侧：页面容器
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True)

        self._container = tk.Frame(right, bg=BG)
        self._container.pack(fill="both", expand=True, padx=(0, 0), pady=0)

        # 状态栏
        status = tk.Frame(right, bg=BG_ALT, height=26)
        status.pack(side="bottom", fill="x")
        status.pack_propagate(False)
        tk.Frame(status, bg=BORDER, height=1).place(x=0, y=0, relwidth=1)
        self._status_var = tk.StringVar(value="就绪")
        tk.Label(status, textvariable=self._status_var, bg=BG_ALT, fg=FG_DIM,
                 font=self.fonts["small"], anchor="w").pack(side="left", padx=12)
        self._status_right = tk.Label(status, text="", bg=BG_ALT, fg=FG_FAINT,
                                      font=self.fonts["small"], anchor="e")
        self._status_right.pack(side="right", padx=12)

        self.toast = Toast(self)
        self._refresh_topbar()

    def _refresh_topbar(self) -> None:
        acc = self.current_account()
        name = acc.name if acc else (self.cfg.get("username") or "Steve")
        premium = acc is not None and acc.premium
        if premium:
            sub = "微软正版账户"
        elif acc is not None and acc.third_party:
            sub = acc.site_name or "第三方账户"
        else:
            sub = "离线账户"
        bar = getattr(self, "_topbar", None)
        if bar is not None:
            bar.set_account(name, sub, premium)
            bar.set_active_key(self._current or "home")
            self._load_avatar(bar.avatar, acc)

    def _build_account(self) -> None:
        """左侧白栏顶部的账户卡（点击进账户管理）。"""
        for w in self._account_frame.winfo_children():
            w.destroy()

        acc = self.current_account()
        name = acc.name if acc else (self.cfg.get("username") or "Steve")
        premium = acc is not None and acc.premium
        if premium:
            subtitle = "微软正版账户"
        elif acc is not None and acc.third_party:
            subtitle = acc.site_name or "第三方账户"
        else:
            subtitle = "离线账户"

        card = tk.Frame(self._account_frame, bg=BG_ALT, cursor="hand2")
        card.pack(fill="x")

        avatar = Avatar(card, size=64, bg=BG_ALT, border=BG_HOVER)
        avatar.pack(pady=(4, 6))
        self._load_avatar(avatar, acc)

        lbl1 = tk.Label(card, text=name, bg=BG_ALT, fg=FG,
                        font=self.fonts["h2"], cursor="hand2")
        lbl1.pack()
        lbl2 = tk.Label(card, text=subtitle, bg=BG_ALT,
                        fg=ACCENT if premium else FG_FAINT,
                        font=self.fonts["small"], cursor="hand2")
        lbl2.pack(pady=(1, 8))

        hint = tk.Label(card, text="切换账户" if len(self._accounts) > 1 else "账户管理",
                        bg=BG_ALT, fg=FG_FAINT, font=self.fonts["small"], cursor="hand2")
        hint.pack(pady=(0, 4))

        for w in (card, avatar, lbl1, lbl2, hint):
            w.bind("<Button-1>", lambda _e: self.open_accounts())
        for w in (card, lbl1, lbl2, hint):
            w.bind("<Enter>", lambda _e: lbl1.configure(fg=ACCENT))
            w.bind("<Leave>", lambda _e: lbl1.configure(fg=FG))

        # 分割线 + 快捷入口
        tk.Frame(self._account_frame, bg=BORDER, height=1).pack(fill="x", pady=(14, 12))
        quick = tk.Frame(self._account_frame, bg=BG_ALT)
        quick.pack(fill="x")
        for text, command in (("游戏目录", self._open_game_dir),
                              ("版本设置", lambda: self.show_page("settings")),
                              ("皮肤管理", self.open_skin_manager)):
            lbl = tk.Label(quick, text=text, bg=BG_ALT, fg=FG_DIM, anchor="w",
                           font=self.fonts["body"], cursor="hand2")
            lbl.pack(fill="x", pady=3)
            lbl.bind("<Button-1>", lambda _e, c=command: c())
            lbl.bind("<Enter>", lambda _e, w=lbl: w.configure(fg=ACCENT))
            lbl.bind("<Leave>", lambda _e, w=lbl: w.configure(fg=FG_DIM))

    def _open_game_dir(self) -> None:
        import os
        import subprocess

        path = self.cfg.game_dir
        try:
            path.mkdir(parents=True, exist_ok=True)
            os.startfile(str(path))
        except Exception:                              # noqa: BLE001
            subprocess.Popen(["explorer", str(path)])

    def _load_avatar(self, avatar, acc) -> None:
        """侧边栏头像：先用首字母，再后台拉真实皮肤的头像。"""
        import threading

        from .. import skins

        name = acc.name if acc is not None else str(self.cfg.get("username") or "Steve")
        avatar.draw_letter(name)
        if acc is None or not acc.uuid:
            return
        api = acc.api if acc.third_party else ""
        uuid = acc.uuid.replace("-", "")

        def work() -> None:
            png = skins.fetch_skin_png(uuid, api)
            if not png:
                return

            def apply() -> None:
                try:
                    avatar.draw_skin(png)
                except tk.TclError:
                    pass

            self.post(apply)

        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------ 账户

    @property
    def accounts(self) -> list:
        return self._accounts

    def current_account(self):
        idx = accounts.current_index(self.cfg, len(self._accounts))
        return self._accounts[idx] if idx >= 0 else None

    @property
    def ms_account(self):
        acc = self.current_account()
        if acc is not None and acc.premium and acc.refresh_token:
            return acc.to_ms()
        return None

    def effective_account(self) -> tuple[str, str, str, str]:
        """启动时用哪个账号：返回 (名字, uuid, access_token, user_type)。"""
        acc = self.current_account()
        if acc is not None and acc.premium and acc.access_token:
            return acc.name, acc.uuid, acc.access_token, "msa"
        if acc is not None and acc.third_party and acc.access_token:
            return acc.name, acc.uuid, acc.access_token, "legacy"
        if acc is not None and acc.kind == "offline":
            uuid = acc.uuid or accounts.offline_uuid(acc.name)
            return acc.name, uuid, "0", "legacy"
        name = str(self.cfg.get("username") or "Steve")
        return name, accounts.offline_uuid(name), "0", "legacy"

    @property
    def skin_account(self):
        """当前账号如果是第三方皮肤站账号，返回可直接用于注入的 SkinAccount。"""
        acc = self.current_account()
        if acc is None or not acc.third_party or not acc.access_token or not acc.api:
            return None
        from ..skin_sites import SkinAccount
        return SkinAccount(name=acc.name, uuid=acc.uuid, access_token=acc.access_token,
                           api=acc.api, site_id=acc.site_id, client_token=acc.client_token)

    def set_skin_account(self, skin, make_current: bool = True) -> None:
        from ..accounts import Account
        self._accounts, idx = accounts.upsert(self._accounts, Account.from_skin(skin),
                                              make_current=make_current)
        accounts.save(self.cfg, self._accounts, idx)
        self.cfg.set("username", skin.name)
        self.cfg.save()
        self.refresh_account()
        self._notify_home()

    def open_skin_login(self) -> None:
        from .skin_dialog import SkinLoginDialog
        dlg = SkinLoginDialog(self, on_done=self.set_skin_account)
        try:
            dlg.grab_set()
        except tk.TclError:
            pass

    def set_ms_account(self, account) -> None:
        from ..accounts import Account
        self._accounts, idx = accounts.upsert(self._accounts, Account.from_ms(account))
        accounts.save(self.cfg, self._accounts, idx)
        self.cfg.set("username", account.name)
        self.cfg.save()
        self.refresh_account()
        self._notify_home()

    def switch_account(self, index: int) -> None:
        if not (0 <= index < len(self._accounts)):
            return
        accounts.save(self.cfg, self._accounts, index)
        acc = self._accounts[index]
        self.cfg.set("username", acc.name)
        self.cfg.save()
        self.refresh_account()
        self._notify_home()

    def add_offline_account(self, name: str):
        from ..accounts import Account
        name = (name or "").strip() or "Steve"
        self._accounts, idx = accounts.upsert(self._accounts, Account.new_offline(name))
        accounts.save(self.cfg, self._accounts, idx)
        self.cfg.set("username", name)
        self.cfg.save()
        self.refresh_account()
        self._notify_home()
        return self._accounts[idx]

    def remove_account(self, index: int) -> None:
        self._accounts, idx = accounts.remove(self._accounts, index)
        accounts.save(self.cfg, self._accounts, idx)
        self.refresh_account()
        self._notify_home()

    def _notify_home(self) -> None:
        page = self._pages.get("home")
        if page is not None and hasattr(page, "on_account_changed"):
            try:
                page.on_account_changed()
            except Exception:                        # noqa: BLE001
                pass

    def open_login(self) -> None:
        from .ms_login import MsLoginDialog
        dlg = MsLoginDialog(self)
        try:
            dlg.grab_set()
        except tk.TclError:
            pass

    def open_accounts(self) -> None:
        from .account_dialog import AccountDialog
        dlg = AccountDialog(self)
        try:
            dlg.grab_set()
        except tk.TclError:
            pass

    def open_skin_manager(self) -> None:
        from .skin_mgr_dialog import SkinDialog
        dlg = SkinDialog(self)
        try:
            dlg.grab_set()
        except tk.TclError:
            pass

    # ------------------------------------------------------------ 图标

    def _set_icon(self) -> None:
        import sys
        from pathlib import Path
        candidates: list[Path] = []
        base = getattr(sys, "_MEIPASS", None)
        if base:
            candidates.append(Path(base) / "assets" / "icon.ico")
        here = Path(__file__).resolve().parent.parent.parent
        candidates.append(here / "assets" / "icon.ico")
        if getattr(sys, "frozen", False):
            candidates.append(Path(sys.executable))
        for c in candidates:
            try:
                if c.is_file():
                    self.iconbitmap(str(c))
                    return
            except (tk.TclError, OSError):
                continue

    # ------------------------------------------------------------ 页面

    def create_pages(self) -> None:
        """建立四个页面。换主题重建界面时会再次调用。"""
        from .page_home import HomePage
        from .page_install import InstallPage
        from .page_mods import ModsPage
        from .page_settings import SettingsPage

        self.register_page("home", HomePage(self._container, self))
        self.register_page("install", InstallPage(self._container, self))
        self.register_page("mods", ModsPage(self._container, self))
        self.register_page("settings", SettingsPage(self._container, self))
        self.after(200, self._setup_dnd)

    # ------------------------------------------------------------ 拖拽

    def _setup_dnd(self) -> None:
        if not self._dnd_ok:
            return
        self.add_drop_target(self)
        self.add_drop_target(self._container)

    def add_drop_target(self, widget) -> None:
        """把 widget 及其所有子控件注册成投放目标。"""
        if not self._dnd_ok or _DND_WRAPPER is None:
            return
        stack = [widget]
        while stack:
            w = stack.pop()
            try:
                _DND_WRAPPER.drop_target_register(w, DND_FILES)
                _DND_WRAPPER.dnd_bind(w, "<<Drop>>", self._on_drop)
            except Exception:                     # noqa: BLE001
                pass
            try:
                stack.extend(w.winfo_children())
            except tk.TclError:
                pass

    def _on_drop(self, event):
        try:
            paths = [Path(p) for p in self.tk.splitlist(event.data)]
        except (tk.TclError, ValueError):
            paths = [Path(str(event.data))]
        self.handle_drop(paths)
        return "copy"

    def handle_drop(self, paths: list[Path]) -> None:
        """拖入文件的统一入口：先给当前页处理，不行就交给 Mod 页。"""
        paths = [p for p in paths if p]
        if not paths:
            return
        page = self._pages.get(self._current)
        if page is not None and hasattr(page, "handle_drop"):
            try:
                page.handle_drop(paths)
                return
            except Exception as exc:              # noqa: BLE001
                self.notify(f"处理拖入文件失败：{exc}", "err")
                return
        mods = self._pages.get("mods")
        if mods is not None and hasattr(mods, "handle_drop"):
            mods.handle_drop(paths)
        else:
            self.notify("这个页面不支持拖入文件", "warn")

    def register_page(self, key: str, page: tk.Frame) -> None:
        self._pages[key] = page

    def show_page(self, key: str) -> None:
        if key not in self._pages:
            return
        if self._current == key:
            return
        if self._current and self._current in self._pages:
            old = self._pages[self._current]
            if hasattr(old, "on_hide"):
                try:
                    old.on_hide()
                except Exception:                    # noqa: BLE001
                    pass
            old.pack_forget()

        page = self._pages[key]
        page.pack(fill="both", expand=True)
        self._current = key
        bar = getattr(self, "_topbar", None)
        if bar is not None:
            bar.set_active_key(key)
        if hasattr(page, "on_show"):
            try:
                page.on_show()
            except Exception:                        # noqa: BLE001
                pass
        # 页面里的控件是 on_show 之后才建出来的，拖拽目标得重新登记一次
        if self._dnd_ok:
            self.after(60, lambda p=page: self.add_drop_target(p))

    def refresh_account(self) -> None:
        self._build_account()
        self._refresh_topbar()

    # ------------------------------------------------------------ 状态栏
    def set_status(self, text: str, right: str = "") -> None:
        try:
            self._status_var.set(text)
            self._status_right.configure(text=right)
        except tk.TclError:
            pass

    def notify(self, text: str, kind: str = "info") -> None:
        try:
            self.toast.show(text, kind)
        except tk.TclError:
            pass

    # ------------------------------------------------------------ 主题

    def apply_theme(self, name: str) -> None:
        """切换配色并就地重建界面（不重启进程）。"""
        from . import theme as th

        name = th.set_theme(name)
        self.cfg.set("theme", name)
        self.cfg.save()
        try:
            self.configure(bg=BG)
        except tk.TclError:
            pass
        # 延后一帧：调用方可能正处在某个按钮的回调里，先让它安全返回
        self.after(30, self._rebuild)

    def _rebuild(self) -> None:
        current = self._current or "home"
        for w in self.winfo_children():
            try:
                w.destroy()
            except tk.TclError:
                pass
        self._pages.clear()
        self._nav.clear()
        self._current = ""
        self._build()
        self.create_pages()
        self.show_page(current if current in self._pages else "home")

    # ------------------------------------------------------------ 重启

    def restart(self) -> None:
        """关掉自己再起一个新进程。"""
        import subprocess
        import sys
        self.cfg.save()
        try:
            if getattr(sys, "frozen", False):
                subprocess.Popen([sys.executable], close_fds=True,
                                 creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
            else:
                entry = Path(__file__).resolve().parent.parent.parent / "main.py"
                subprocess.Popen([sys.executable, str(entry)], cwd=str(entry.parent),
                                 close_fds=True,
                                 creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
        except OSError as exc:
            messagebox.showerror("重启失败", f"请手动重新打开启动器。\n\n{exc}", parent=self)
            return
        self.destroy()

    # ------------------------------------------------------------ 关闭

    def on_close(self) -> None:
        if self._running_task:
            if not messagebox.askyesno("确认退出", "仍有任务在进行，确定要退出吗？", parent=self):
                return
        self.cfg.save()
        self.destroy()

