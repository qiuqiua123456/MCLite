"""皮肤管理弹窗：看当前皮肤、上传本地 PNG、重置、跳到皮肤站衣柜。"""

from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox

from .theme import BG, BG_ALT, BORDER, DANGER, FG, FG_DIM, FG_FAINT, SUCCESS, FlatButton
from .widgets import Avatar, LogPanel


def _reachable(url: str, timeout: float = 4.0) -> tuple[bool, str]:
    """粗探一下网址能不能连上：能收到任何 HTTP 响应（含 4xx）就算通。"""
    import urllib.error
    import urllib.parse
    import urllib.request

    if urllib.parse.urlparse(url).scheme not in ("http", "https"):
        return False, "不是 http(s) 地址"
    req = urllib.request.Request(url, method="HEAD", headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, f"HTTP {resp.status}"
    except urllib.error.HTTPError as exc:
        return True, f"HTTP {exc.code}"
    except Exception as exc:                            # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


class SkinDialog(tk.Toplevel):
    def __init__(self, app) -> None:
        super().__init__(app)
        self.app = app
        self._busy = False
        self._png: bytes | None = None
        self.title("皮肤管理")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(app)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Escape>", lambda _e: self._close())
        self._build()
        self._center()
        self.after(100, self.reload)

    # ------------------------------------------------------------ 布局

    def _build(self) -> None:
        pad = tk.Frame(self, bg=BG, padx=20, pady=16)
        pad.pack(fill="both", expand=True)

        head = tk.Frame(pad, bg=BG)
        head.pack(fill="x")
        tk.Label(head, text="皮肤管理", bg=BG, fg=FG,
                 font=self.app.fonts["h2"]).pack(side="left")

        body = tk.Frame(pad, bg=BG)
        body.pack(fill="x", pady=(12, 0))

        box = tk.Frame(body, bg=BG_ALT, highlightthickness=1, highlightbackground=BORDER,
                       padx=14, pady=12)
        box.pack(side="left")
        self._avatar = Avatar(box, size=96, bg=BG_ALT, border=BORDER)
        self._avatar.pack()

        info = tk.Frame(body, bg=BG)
        info.pack(side="left", fill="both", expand=True, padx=(16, 0))
        self._name = tk.Label(info, text="", bg=BG, fg=FG, font=self.app.fonts["body"],
                              anchor="w")
        self._name.pack(fill="x")
        self._kind = tk.Label(info, text="", bg=BG, fg=FG_DIM, font=self.app.fonts["small"],
                              anchor="w")
        self._kind.pack(fill="x", pady=(4, 0))
        self._uuid = tk.Label(info, text="", bg=BG, fg=FG_FAINT, font=("Consolas", 9),
                              anchor="w")
        self._uuid.pack(fill="x", pady=(2, 0))
        self._hint = tk.Label(info, text="", bg=BG, fg=FG_DIM, font=self.app.fonts["small"],
                              anchor="w", justify="left", wraplength=330)
        self._hint.pack(fill="x", pady=(10, 0))

        tools = tk.Frame(pad, bg=BG)
        tools.pack(fill="x", pady=(14, 0))
        self._up_btn = FlatButton(tools, "上传皮肤…", command=self._upload,
                                  kind="primary", height=32, width=96, bg=BG)
        self._up_btn.pack(side="left")
        self._reset_btn = FlatButton(tools, "重置皮肤", command=self._reset, kind="normal",
                                     height=32, width=88, bg=BG)
        self._reset_btn.pack(side="left", padx=8)
        self._lobby_btn = FlatButton(tools, "打开衣柜", command=self._lobby, kind="ghost",
                                     height=32, width=88, bg=BG)
        self._lobby_btn.pack(side="left")
        self._namemc_btn = FlatButton(tools, "NameMC 查看", command=self._namemc,
                                      kind="ghost", height=32, width=104, bg=BG)
        self._namemc_btn.pack(side="left", padx=8)
        FlatButton(tools, "刷新", command=self.reload, kind="ghost", height=32, width=64,
                   bg=BG).pack(side="left")
        FlatButton(tools, "关闭", command=self._close, kind="normal", height=32, width=72,
                   bg=BG).pack(side="right")

        self._log = LogPanel(pad, height=5)
        self._log.pack(fill="x", pady=(10, 0))

    def _center(self) -> None:
        self.update_idletasks()
        w, h = 560, 400
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2 - 30}")

    # ------------------------------------------------------------ 数据

    def _account(self):
        acc = self.app.current_account()
        return acc

    def reload(self) -> None:
        acc = self._account()
        if acc is None:
            self._name.configure(text="没有账号")
            self._hint.configure(text="先在左下角登录账号。")
            self._set_enabled(False)
            return
        self._name.configure(text=acc.name)
        self._kind.configure(text=acc.label)
        self._uuid.configure(text=acc.short_uuid() or "—")
        self._set_enabled(True)
        if acc.premium or acc.third_party:
            self._load_remote(acc)
        else:
            self._avatar.clear()
            self._hint.configure(text="离线账号没有皮肤数据。\n登录微软账号或皮肤站账号后可以在线换皮肤。")

    def _load_remote(self, acc) -> None:
        from .. import skins

        api = getattr(acc, "api", "") or ""
        self._hint.configure(text="正在读取皮肤…")
        self._up_btn.set_enabled(False)

        def work() -> None:
            try:
                png = skins.fetch_skin_png(acc.uuid, api)
                err = ""
            except Exception as exc:                   # noqa: BLE001
                png, err = None, str(exc) or "对方没有返回皮肤"
            self.app.post(lambda: self._show(png, err, acc))

        threading.Thread(target=work, daemon=True).start()

    def _show(self, png: bytes | None, err: str, acc) -> None:
        self._png = png
        if png:
            self._avatar.draw_skin(png)
            self._hint.configure(text="已读取到当前皮肤。可以上传新的 64x64 PNG 皮肤文件。",
                                 fg=SUCCESS)
        else:
            self._avatar.clear()
            self._hint.configure(text=f"没读到皮肤：{err}", fg=FG_DIM)
        self._up_btn.set_enabled(not self._busy)

    def _set_enabled(self, value: bool) -> None:
        for btn in (self._up_btn, self._reset_btn, self._lobby_btn):
            btn.set_enabled(value and not self._busy)

    # ------------------------------------------------------------ 动作

    def _upload(self) -> None:
        acc = self._account()
        if acc is None:
            return
        from .. import skins

        if not acc.premium:
            self.app.notify("第三方皮肤站请点「打开衣柜」在网页上传", "info")
            self._lobby()
            return
        path = filedialog.askopenfilename(parent=self, title="选择皮肤 PNG",
                                          filetypes=[("PNG 图片", "*.png")])
        if not path:
            return
        try:
            png = Path(path).read_bytes()
        except OSError as exc:
            self.app.notify(f"读取失败：{exc}", "err")
            return
        if len(png) < 100 or png[:8] != b"\x89PNG\r\n\x1a\n":
            messagebox.showerror("不是 PNG", "皮肤文件必须是 PNG 图片。", parent=self)
            return
        self._busy = True
        self._set_enabled(False)
        self._log.write(f"正在上传 {Path(path).name} …")

        def work() -> None:
            try:
                skins.upload(acc.uuid, acc.access_token, png)
            except Exception as exc:                   # noqa: BLE001
                msg = str(exc)
                self.app.post(lambda: self._done(f"上传失败：{msg}", False))
                return
            self.app.post(lambda: self._done("皮肤已更新", True))

        threading.Thread(target=work, daemon=True).start()

    def _reset(self) -> None:
        acc = self._account()
        if acc is None:
            return
        from .. import skins

        if not acc.premium:
            self._lobby()
            return
        if not messagebox.askyesno("重置皮肤", "把皮肤恢复成默认的 Steve / Alex？", parent=self):
            return
        self._busy = True
        self._set_enabled(False)

        def work() -> None:
            try:
                skins.reset(acc.uuid, acc.access_token)
            except Exception as exc:                   # noqa: BLE001
                msg = str(exc)
                self.app.post(lambda: self._done(f"重置失败：{msg}", False))
                return
            self.app.post(lambda: self._done("皮肤已重置", True))

        threading.Thread(target=work, daemon=True).start()

    def _done(self, msg: str, ok: bool) -> None:
        self._busy = False
        self._log.write(msg)
        self.app.notify(msg, "ok" if ok else "err")
        self._set_enabled(True)
        self.reload()

    def _lobby(self) -> None:
        acc = self._account()
        site = getattr(acc, "site_id", "") if acc else ""
        if site:
            from ..skin_sites import SITE_BY_ID
            item = SITE_BY_ID.get(site)
            url = f"{item.api.split('/api/')[0]}/user/closet" if item else ""
        else:
            url = "https://www.minecraft.net/zh-hans/msaprofile/mygames/editskin"
        if not url:
            return
        self._log.write(f"衣柜地址：{url}")
        self._log.write("先探一下本机能不能连上…")

        def work() -> None:
            ok, reason = _reachable(url)
            self.app.post(lambda: self._after_lobby(url, ok, reason))

        threading.Thread(target=work, daemon=True).start()

    def _after_lobby(self, url: str, ok: bool, reason: str) -> None:
        if ok:
            webbrowser.open(url)
            self._log.write("已在浏览器打开衣柜页面")
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(url)
        except tk.TclError:
            pass
        self._log.write(f"本机连不上（{reason}），网址已复制到剪贴板")
        messagebox.showwarning(
            "这个网址本机打不开",
            f"{url}\n\n探测结果：{reason}\n网址已经复制到剪贴板，"
            f"可以换个网络 / 挂代理后在浏览器里粘贴打开。\n\n"
            f"只想看当前皮肤的话，点「NameMC 查看」更省事。",
            parent=self)

    def _namemc(self) -> None:
        acc = self._account()
        uuid = getattr(acc, "uuid", "") if acc else ""
        if not uuid:
            self._log.write("当前账号没有 UUID，看不了 NameMC")
            return
        url = f"https://namemc.com/profile/{uuid}"
        webbrowser.open(url)
        self._log.write(f"已在浏览器打开 NameMC 皮肤页：{url}")

    def _close(self) -> None:
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
