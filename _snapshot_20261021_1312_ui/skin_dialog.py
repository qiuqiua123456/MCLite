"""第三方皮肤站登录（Yggdrasil）：选站点 → 打开认证页面 → 邮箱密码登录。

登录成功后账号会被保存，启动游戏时自动加 ``-javaagent:authlib-injector``，
于是一个人也能用上第三方的皮肤 / 披风。
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from .. import skin_sites
from .theme import (
    ACCENT, BG, BG_ALT, BORDER, FG, FG_DIM, FG_FAINT, SUCCESS, WARN,
    FlatButton, ScrollFrame,
)


class SkinLoginDialog(tk.Toplevel):
    def __init__(self, app, on_done=None):
        super().__init__(app)
        self.app = app
        self._on_done = on_done
        self._busy = False
        self._site = skin_sites.SITES[0]
        self._site_btns: dict[str, FlatButton] = {}
        self.title("第三方皮肤站登录")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.geometry("600x460")
        self.transient(app)
        self._build()
        self._center()
        self.bind("<Escape>", lambda _e: self.destroy())

    # ------------------------------------------------------------ 布局

    def _center(self) -> None:
        self.update_idletasks()
        try:
            px, py = self.app.winfo_rootx(), self.app.winfo_rooty()
            pw, ph = self.app.winfo_width(), self.app.winfo_height()
            w, h = self.winfo_width(), self.winfo_height()
            self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 3}")
        except tk.TclError:
            pass

    def _build(self) -> None:
        pad = tk.Frame(self, bg=BG, padx=24, pady=20)
        pad.pack(fill="both", expand=True)

        tk.Label(pad, text="第三方皮肤站登录", bg=BG, fg=FG,
                 font=self.app.fonts["h1"], anchor="w").pack(fill="x")
        tk.Label(pad, text="用皮肤站账号登录后，游戏里就会显示这个站点的皮肤 / 披风。",
                 bg=BG, fg=FG_DIM, font=self.app.fonts["small"],
                 anchor="w").pack(fill="x", pady=(4, 14))

        # 站点选择
        tk.Label(pad, text="皮肤站", bg=BG, fg=FG_DIM,
                 font=self.app.fonts["small"], anchor="w").pack(fill="x")
        row = tk.Frame(pad, bg=BG)
        row.pack(fill="x", pady=(6, 0))
        for site in skin_sites.SITES:
            btn = FlatButton(row, site.name, command=lambda s=site: self._pick_site(s),
                             kind="primary" if site is self._site else "normal",
                             height=30, width=104, bg=BG)
            btn.pack(side="left", padx=(0, 8))
            self._site_btns[site.id] = btn
        FlatButton(row, "自定义…", command=self._custom_site, kind="ghost",
                   height=30, width=84, bg=BG).pack(side="left")

        self._site_note = tk.Label(pad, text="", bg=BG, fg=FG_FAINT,
                                   font=self.app.fonts["small"], anchor="w")
        self._site_note.pack(fill="x", pady=(6, 0))

        # 浏览器提示
        link = tk.Frame(pad, bg=BG_ALT)
        link.pack(fill="x", pady=(12, 0))
        inner = tk.Frame(link, bg=BG_ALT, padx=12, pady=10)
        inner.pack(fill="x")
        self._page_label = tk.Label(inner, text="", bg=BG_ALT, fg=FG_DIM,
                                    font=self.app.fonts["small"], anchor="w",
                                    justify="left")
        self._page_label.pack(side="left", fill="x", expand=True)
        # 不自动跳浏览器：由用户点这个按钮才会打开认证页面
        self._open_btn = FlatButton(inner, "打开认证页面", command=self._open_page,
                                    kind="primary", height=28, width=104, bg=BG_ALT)
        self._open_btn.pack(side="right", padx=(10, 0))

        # 账号密码
        form = tk.Frame(pad, bg=BG)
        form.pack(fill="x", pady=(14, 0))

        tk.Label(form, text="邮箱 / 角色名", bg=BG, fg=FG_DIM, anchor="w",
                 font=self.app.fonts["small"]).grid(row=0, column=0, sticky="w")
        self._user_var = tk.StringVar()
        tk.Entry(form, textvariable=self._user_var, bg=BG_ALT, fg=FG, insertbackground=FG,
                 bd=0, highlightthickness=1, highlightbackground=BORDER,
                 highlightcolor=BORDER, font=self.app.fonts["body"]).grid(
            row=1, column=0, sticky="ew", ipady=6, pady=(4, 10))

        tk.Label(form, text="密码", bg=BG, fg=FG_DIM, anchor="w",
                 font=self.app.fonts["small"]).grid(row=2, column=0, sticky="w")
        self._pass_var = tk.StringVar()
        self._pass_entry = tk.Entry(form, textvariable=self._pass_var, show="●",
                                    bg=BG_ALT, fg=FG, insertbackground=FG,
                                    bd=0, highlightthickness=1, highlightbackground=BORDER,
                                    highlightcolor=BORDER, font=self.app.fonts["body"])
        self._pass_entry.grid(row=3, column=0, sticky="ew", ipady=6, pady=(4, 10))
        self._pass_entry.bind("<Return>", lambda _e: self._login())
        form.columnconfigure(0, weight=1)

        # 底部
        bottom = tk.Frame(pad, bg=BG)
        bottom.pack(fill="x", side="bottom")
        self._status = tk.Label(bottom, text="", bg=BG, fg=FG_DIM,
                                font=self.app.fonts["small"], anchor="w")
        self._status.pack(side="left", fill="x", expand=True)
        self._login_btn = FlatButton(bottom, "登录", command=self._login, kind="primary",
                                     height=34, width=110, bg=BG)
        self._login_btn.pack(side="right")

        self._pick_site(self._site, open_page=False)

    # ------------------------------------------------------------ 站点

    def _pick_site(self, site, open_page: bool = False) -> None:
        self._site = site
        for sid, btn in self._site_btns.items():
            btn.kind = "primary" if sid == site.id else "normal"
            btn._draw()
        self._site_note.configure(text=f"{site.note}   API：{site.api}")
        self._page_label.configure(text=f"认证页面：{site.auth_url}\n"
                                        f"（要注册 / 改皮肤时点右边按钮打开，不会自动跳转）")
        if open_page:
            self._open_page()

    def _custom_site(self) -> None:
        from tkinter import simpledialog
        url = simpledialog.askstring(
            "自定义皮肤站", "填这个皮肤站的 Yggdrasil API 地址：\n"
                          "（一般形如 https://example.com/api/yggdrasil）",
            parent=self)
        if not url:
            return
        try:
            site = skin_sites.custom_site(url)
        except skin_sites.SkinError as exc:
            messagebox.showerror("地址不对", str(exc), parent=self)
            return
        self._pick_site(site)

    def _open_page(self) -> None:
        url = skin_sites.open_auth_page(self._site)
        if url:
            self._page_label.configure(text=f"认证页面（已用浏览器打开）：\n{url}")
        else:
            self._page_label.configure(text=f"已复制认证页面网址：\n{self._site.auth_url}")

    # ------------------------------------------------------------ 登录

    def _set_status(self, text: str, color: str = FG_DIM) -> None:
        try:
            self._status.configure(text=text, fg=color)
        except tk.TclError:
            pass

    def _login(self) -> None:
        if self._busy:
            return
        user = self._user_var.get().strip()
        password = self._pass_var.get()
        if not user or not password:
            self._set_status("请填写邮箱和密码", WARN)
            return
        self._busy = True
        self._login_btn.set_enabled(False)
        self._set_status("正在登录皮肤站…")
        site = self._site

        import threading

        def work() -> None:
            try:
                acc = skin_sites.authenticate(site, user, password)
            except skin_sites.SkinError as exc:
                self.app.post(lambda: self._on_failed(str(exc)))
                return
            self.app.post(lambda: self._on_ok(acc))

        threading.Thread(target=work, daemon=True).start()

    def _on_failed(self, msg: str) -> None:
        self._busy = False
        self._login_btn.set_enabled(True)
        self._set_status(f"登录失败：{msg}", WARN)

    def _on_ok(self, acc) -> None:
        self._busy = False
        self._login_btn.set_enabled(True)
        self._set_status(f"登录成功：{acc.name}（{acc.site_name}）", SUCCESS)
        if self._on_done:
            try:
                self._on_done(acc)
            except Exception:                        # noqa: BLE001
                pass
        self.app.notify(f"已登录 {acc.site_name}：{acc.name}", "ok")
        self.after(400, self.destroy)


class SkinInjectorDialog(tk.Toplevel):
    """（预留）显示 authlib-injector 的下载进度。"""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("正在准备 authlib-injector")
        self.configure(bg=BG)
        self.geometry("420x120")
        tk.Label(self, text="正在下载 authlib-injector…", bg=BG, fg=FG,
                 font=app.fonts["body"]).pack(pady=30)
