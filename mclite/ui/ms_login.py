"""微软正版登录弹窗：设备码流程，玩家在浏览器里授权一次即可。"""

from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox

from .. import auth
from .theme import (
    ACCENT, BG, BG_ALT, BORDER, DANGER, FG, FG_DIM, FG_FAINT, SUCCESS,
    FlatButton, round_rect,
)


class MsLoginDialog(tk.Toplevel):
    """两种状态：等待授权 / 已登录。"""

    def __init__(self, app) -> None:
        super().__init__(app)
        self.app = app
        self.title("微软正版登录")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(app)
        self._cancel = threading.Event()
        self._login: auth.DeviceLogin | None = None
        self._status_var = tk.StringVar(value="")

        self._build()
        self._center()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Escape>", lambda _e: self._on_close())

        if self.app.ms_account is not None:
            self._show_logged_in()
        else:
            self.after(120, self._start)

    # ------------------------------------------------------------ 布局

    def _build(self) -> None:
        pad = tk.Frame(self, bg=BG, padx=22, pady=18)
        pad.pack(fill="both", expand=True)

        tk.Label(pad, text="微软正版登录", bg=BG, fg=FG,
                 font=self.app.fonts["h2"]).pack(anchor="w")
        tk.Label(pad, text="登录后可进入需要正版验证的服务器，并同步你的皮肤和 ID",
                 bg=BG, fg=FG_FAINT, font=self.app.fonts["small"]).pack(anchor="w", pady=(3, 14))

        self._body = tk.Frame(pad, bg=BG)
        self._body.pack(fill="both", expand=True)

        # ---- 等待授权区
        self._wait_box = tk.Frame(self._body, bg=BG)

        step1 = tk.Frame(self._wait_box, bg=BG)
        step1.pack(fill="x")
        tk.Label(step1, text="① 浏览器打开下面的网址（已自动帮你打开）", bg=BG, fg=FG_DIM,
                 font=self.app.fonts["body"]).pack(anchor="w")
        self._uri_label = tk.Label(step1, text="https://www.microsoft.com/link", bg=BG,
                                   fg=ACCENT, font=self.app.fonts["body"], cursor="hand2")
        self._uri_label.pack(anchor="w", padx=(18, 0), pady=(2, 0))
        self._uri_label.bind("<Button-1>", lambda _e: self._open_browser())

        tk.Label(self._wait_box, text="② 输入下面的代码", bg=BG, fg=FG_DIM,
                 font=self.app.fonts["body"]).pack(anchor="w", pady=(14, 0))

        code_wrap = tk.Frame(self._wait_box, bg=BG)
        code_wrap.pack(fill="x", pady=(4, 0))
        self._code_canvas = tk.Canvas(code_wrap, height=62, bg=BG, highlightthickness=0, bd=0)
        self._code_canvas.pack(side="left")
        self._copy_btn = FlatButton(code_wrap, "复制代码", command=self._copy_code,
                                    kind="normal", height=34, width=96,
                                    font=self.app.fonts["small"], bg=BG)
        self._copy_btn.pack(side="left", padx=(10, 0), pady=(14, 0))
        self._copy_btn.set_enabled(False)

        self._retry_btn = FlatButton(self._wait_box, "重新获取代码", command=self._start,
                                     kind="normal", height=30, width=118,
                                     font=self.app.fonts["small"], bg=BG)

        self._status = tk.Label(self._wait_box, textvariable=self._status_var, bg=BG,
                                fg=FG_DIM, font=self.app.fonts["small"], anchor="w",
                                justify="left", wraplength=420)
        self._status.pack(fill="x", pady=(14, 0))

        # ---- 已登录区
        self._done_box = tk.Frame(self._body, bg=BG)
        self._name_label = tk.Label(self._done_box, text="", bg=BG, fg=FG,
                                    font=("Segoe UI", 16, "bold"), anchor="w")
        self._name_label.pack(anchor="w")
        self._uuid_label = tk.Label(self._done_box, text="", bg=BG, fg=FG_FAINT,
                                    font=self.app.fonts["small"], anchor="w")
        self._uuid_label.pack(anchor="w", pady=(2, 12))
        tk.Label(self._done_box,
                 text="启动游戏时会自动使用这个正版账号（令牌过期会自动续期）",
                 bg=BG, fg=FG_DIM, font=self.app.fonts["small"]).pack(anchor="w")

        # ---- 底部按钮
        bottom = tk.Frame(pad, bg=BG)
        bottom.pack(fill="x", pady=(16, 0))
        self._close_btn = FlatButton(bottom, "关闭", command=self._on_close, kind="normal",
                                     height=32, width=88, bg=BG)
        self._close_btn.pack(side="right")
        self._logout_btn = FlatButton(bottom, "退出登录", command=self._logout, kind="danger",
                                      height=32, width=96, bg=BG)
        self._again_btn = FlatButton(bottom, "换一个账号", command=self._start, kind="primary",
                                     height=32, width=110, bg=BG)

    def _center(self) -> None:
        self.update_idletasks()
        w, h = 560, 372
        px, py = self.app.winfo_rootx(), self.app.winfo_rooty()
        pw, ph = self.app.winfo_width(), self.app.winfo_height()
        x = px + max(0, (pw - w) // 2)
        y = py + max(0, (ph - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    # ------------------------------------------------------------ 状态切换

    def _show_waiting(self) -> None:
        self._done_box.pack_forget()
        self._again_btn.pack_forget()
        self._logout_btn.pack_forget()
        self._wait_box.pack(fill="both", expand=True)
        self._retry_btn.pack_forget()

    def _show_logged_in(self) -> None:
        acc = self.app.ms_account
        self._wait_box.pack_forget()
        self._done_box.pack(fill="both", expand=True)
        self._again_btn.pack(side="right", padx=(0, 8))
        self._logout_btn.pack(side="right", padx=(0, 8))
        if acc:
            self._name_label.configure(text=acc.name)
            self._uuid_label.configure(text=f"UUID  {acc.uuid}")

    # ------------------------------------------------------------ 登录流程

    def _start(self) -> None:
        self._cancel.clear()
        self._show_waiting()
        self._draw_code("", placeholder="…")
        self._copy_btn.set_text("复制代码")
        self._status_var.set("正在向微软申请登录代码…")
        self._status.configure(fg=FG_DIM)

        def work():
            try:
                login = auth.begin()
            except auth.AuthError as exc:
                self._post(lambda m=str(exc): self._fail(m))
                return
            self._post(lambda: self._on_code(login))

            def on_status(msg: str) -> None:
                self._post(lambda m=msg: self._status_var.set(m))

            try:
                account = auth.wait_for_account(
                    login, on_status, cancelled=self._cancel.is_set)
            except auth.AuthError as exc:
                if not self._cancel.is_set():
                    self._post(lambda m=str(exc): self._fail(m))
                return
            if not self._cancel.is_set():
                self._post(lambda: self._on_success(account))

        threading.Thread(target=work, daemon=True).start()

    def _post(self, fn) -> None:
        try:
            self.app.post(fn)
        except tk.TclError:
            pass

    def _on_code(self, login: auth.DeviceLogin) -> None:
        if not self.winfo_exists():
            return
        self._login = login
        self._draw_code(login.user_code)
        self._copy_code()
        self._open_browser()

    def _on_success(self, account: auth.MsAccount) -> None:
        self.app.set_ms_account(account)
        self.app.notify(f"已登录：{account.name}", "ok")
        self._show_logged_in()

    def _fail(self, message: str) -> None:
        if not self.winfo_exists():
            return
        self._status_var.set(message)
        self._status.configure(fg=DANGER)
        self._retry_btn.pack(anchor="w", pady=(12, 0))

    def _draw_code(self, code: str, placeholder: str = "") -> None:
        c = self._code_canvas
        self._code_text = code
        c.delete("all")
        text = code or placeholder
        if len(text) >= 8:
            text = text[:4] + "-" + text[4:]
        font = ("Consolas", 26, "bold")
        width = max(200, len(text) * 22 + 40)
        c.configure(width=width)
        round_rect(c, 1, 1, width - 1, 61, 8, fill=BG_ALT, outline=BORDER)
        c.create_text(width / 2, 31, text=text, fill=ACCENT if code else FG_FAINT, font=font)
        try:
            self._copy_btn.set_enabled(bool(code))
        except tk.TclError:
            pass

    def _copy_code(self) -> None:
        """一键复制设备码：复制成功后在状态行给出反馈，方便粘到浏览器里。"""
        code = getattr(self, "_code_text", "") or ""
        if not code:
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(code)
            self.update_idletasks()
        except tk.TclError:
            pass
        pretty = code[:4] + "-" + code[4:] if len(code) >= 8 else code
        self._status_var.set(f"已复制代码 {pretty}，粘到浏览器页面即可（授权中…）")
        self._status.configure(fg=SUCCESS)
        self._copy_btn.set_text("已复制")

    def _open_browser(self) -> None:
        import os
        if os.environ.get("MCLITE_NO_BROWSER"):
            return
        uri = self._login.verification_uri if self._login else "https://www.microsoft.com/link"
        try:
            webbrowser.open(uri)
        except Exception:                            # noqa: BLE001
            pass

    # ------------------------------------------------------------ 退出

    def _logout(self) -> None:
        if not messagebox.askyesno("退出登录", "确定要退出微软账号吗？", parent=self):
            return
        self.app.set_ms_account(None)
        self.app.notify("已退出微软账号", "warn")
        self.destroy()

    def _on_close(self) -> None:
        self._cancel.set()
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
