"""账号管理弹窗：多账号列表 + 切换 / 复制 UUID / 删除，以及添加离线账号、微软登录。"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog

from .theme import (
    ACCENT, BG, BG_ALT, BG_HOVER, BORDER, DANGER, FG, FG_DIM, FG_FAINT, SUCCESS,
    FlatButton,
)
from .widgets import ScrollFrame


class AccountDialog(tk.Toplevel):
    def __init__(self, app) -> None:
        super().__init__(app)
        self.app = app
        self.title("账号管理")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(app)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Escape>", lambda _e: self._close())
        self._build()
        self._center()
        self._reload()

    # ------------------------------------------------------------ 布局

    def _build(self) -> None:
        pad = tk.Frame(self, bg=BG, padx=22, pady=18)
        pad.pack(fill="both", expand=True)

        tk.Label(pad, text="账号管理", bg=BG, fg=FG,
                 font=("Segoe UI", 15, "bold")).pack(anchor="w")
        tk.Label(pad,
                 text="同一个启动器里可以存多个账号，随时切换；离线账号的 UUID 也能复制出来给服务器白名单用。",
                 bg=BG, fg=FG_DIM, font=self.app.fonts["small"],
                 wraplength=690, justify="left").pack(anchor="w", pady=(4, 12))

        # 底部按钮先 pack（side="bottom"），保证它一定拿到高度，
        # 否则 holder 的 expand 会把空间吃光、按钮被挤出窗口。
        bottom = tk.Frame(pad, bg=BG)
        bottom.pack(side="bottom", fill="x", pady=(14, 0))
        self._ms_btn = FlatButton(bottom, "微软正版登录", command=self._ms_login,
                                  kind="primary", height=38, width=136, bg=BG)
        self._ms_btn.pack(side="left")
        self._skin_btn = FlatButton(bottom, "第三方皮肤站登录", command=self._skin_login,
                                    kind="primary", height=38, width=152, bg=BG)
        self._skin_btn.pack(side="left", padx=(8, 0))
        self._add_btn = FlatButton(bottom, "添加离线账号", command=self._add_offline,
                                   kind="normal", height=38, width=118, bg=BG)
        self._add_btn.pack(side="left", padx=(8, 0))

        self._close_btn = FlatButton(bottom, "关闭", command=self._close, kind="normal",
                                     height=38, width=80, bg=BG)
        self._close_btn.pack(side="right")
        self._skin_mgr_btn = FlatButton(bottom, "皮肤管理", command=self._skin_manager,
                                        kind="normal", height=38, width=96, bg=BG)
        self._skin_mgr_btn.pack(side="right", padx=(0, 8))

        holder = tk.Frame(pad, bg=BG_ALT, highlightthickness=1,
                          highlightbackground=BORDER)
        holder.pack(fill="both", expand=True)
        self._scroll = ScrollFrame(holder, bg=BG_ALT, height=232)
        self._scroll.pack(fill="both", expand=True, padx=1, pady=1)

    def _skin_manager(self) -> None:
        self.app.open_skin_manager()

    def _center(self) -> None:
        self.update_idletasks()
        w, h = 780, 452
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2 - 40}")

    # ------------------------------------------------------------ 列表

    def _reload(self) -> None:
        for w in self._scroll.inner.winfo_children():
            w.destroy()
        items = self.app.accounts
        cur = self.app.current_account()
        if not items:
            tk.Label(self._scroll.inner, text="还没有账号，先添加一个吧。", bg=BG_ALT,
                     fg=FG_FAINT, font=self.app.fonts["small"]).pack(pady=30)
            return
        for i, acc in enumerate(items):
            self._row(i, acc, cur is not None and acc.uuid == cur.uuid and acc.kind == cur.kind)

    def _row(self, index: int, acc, active: bool) -> None:
        bg = BG_HOVER if active else BG_ALT
        row = tk.Frame(self._scroll.inner, bg=bg, pady=6, padx=12)
        row.pack(fill="x")
        tk.Frame(row, bg=BORDER, height=1).pack(fill="x", pady=(0, 7))

        head = tk.Frame(row, bg=bg)
        head.pack(fill="x")
        dot = tk.Canvas(head, width=10, height=10, bg=bg, highlightthickness=0, bd=0)
        dot.pack(side="left", pady=(5, 0))
        dot.create_oval(1, 1, 9, 9, fill=ACCENT if active else FG_FAINT, outline="")
        tk.Label(head, text=acc.name, bg=bg, fg=FG,
                 font=self.app.fonts["body"]).pack(side="left", padx=(8, 0))
        tk.Label(head, text=acc.label, bg=bg,
                 fg=ACCENT if acc.premium else FG_DIM,
                 font=self.app.fonts["small"]).pack(side="left", padx=(8, 0))
        if active:
            tk.Label(head, text="使用中", bg=bg, fg=SUCCESS,
                     font=self.app.fonts["small"]).pack(side="left", padx=(8, 0))

        FlatButton(head, "删除", command=lambda i=index: self._remove(i),
                   kind="danger", height=24, width=54,
                   font=self.app.fonts["small"], bg=bg).pack(side="right")
        FlatButton(head, "复制 UUID", command=lambda a=acc: self._copy_uuid(a),
                   kind="ghost", height=24, width=82,
                   font=self.app.fonts["small"], bg=bg).pack(side="right", padx=6)
        if not active:
            FlatButton(head, "使用", command=lambda i=index: self._use(i),
                       kind="normal", height=24, width=54,
                       font=self.app.fonts["small"], bg=bg).pack(side="right")

        tk.Label(row, text=acc.short_uuid(), bg=bg, fg=FG_FAINT,
                 font=("Consolas", 9)).pack(anchor="w", padx=(18, 0), pady=(2, 0))

    # ------------------------------------------------------------ 操作

    def _use(self, index: int) -> None:
        self.app.switch_account(index)
        self._reload()
        acc = self.app.current_account()
        self.app.notify(f"已切换到 {acc.name}" if acc else "已切换账号", "ok")

    def _copy_uuid(self, acc) -> None:
        uuid = acc.short_uuid()
        try:
            self.clipboard_clear()
            self.clipboard_append(uuid)
            self.update_idletasks()
        except tk.TclError:
            return
        self.app.notify(f"已复制 UUID：{uuid}", "ok")

    def _remove(self, index: int) -> None:
        acc = self.app.accounts[index] if 0 <= index < len(self.app.accounts) else None
        if acc is None:
            return
        if not messagebox.askyesno("删除账号", f"确定要删除账号「{acc.name}」吗？", parent=self):
            return
        self.app.remove_account(index)
        self._reload()

    def _add_offline(self) -> None:
        name = simpledialog.askstring("添加离线账号", "玩家名：", parent=self,
                                      initialvalue="Steve")
        if not name:
            return
        acc = self.app.add_offline_account(name.strip())
        self._reload()
        self.app.notify(f"已添加离线账号 {acc.name}", "ok")

    def _ms_login(self) -> None:
        from .ms_login import MsLoginDialog
        dlg = MsLoginDialog(self.app)
        try:
            dlg.grab_set()
            self.wait_window(dlg)
        except tk.TclError:
            pass
        self._reload()

    def _skin_login(self) -> None:
        from .skin_dialog import SkinLoginDialog
        dlg = SkinLoginDialog(self.app, on_done=self.app.set_skin_account)
        try:
            dlg.grab_set()
            self.wait_window(dlg)
        except tk.TclError:
            pass
        self._reload()

    def _close(self) -> None:
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
