"""内嵌式账号管理面板：多账号列表 + 切换 / 复制 UUID / 删除，以及登录入口。

从 ``account_dialog.py`` 的 ``AccountDialog`` 移植而来，改成可以贴在开始页里
当标签页用的一个 ``tk.Frame``：不创建窗口、不 ``grab_set``、不 ``wait_window``，
所有账号数据都走 ``app`` 上的现成接口（存储逻辑仍然只留在 ``..accounts``）。

列表里的头像沿用 ``app.py::_load_avatar`` 的做法：先用首字母占位，再由后台
线程拉真实皮肤，最后通过 ``app.post`` 回到主线程画上去。
"""

from __future__ import annotations

import re
import threading
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, simpledialog

from .theme import (
    ACCENT, BG, BG_ALT, BG_HOVER, BORDER, DANGER, FG, FG_DIM, FG_FAINT,
    SUCCESS, FlatButton,
)
from .widgets import Avatar, ScrollFrame, SelectableRow

#: 离线玩家名规则：Minecraft 只认 3~16 位的字母 / 数字 / 下划线
NAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,16}$")


class AccountsPanel(tk.Frame):
    """账号管理面板（内嵌版，没有窗口装饰）。"""

    def __init__(self, master, app, on_log: Callable[[str], None] | None = None):
        super().__init__(master, bg=BG)
        self.app = app
        #: 可选的日志回调，用来把「已切换到 xx」之类的信息写到父级
        self._on_log = on_log
        #: 被销毁后不再重建列表（避免 after 回调打到死控件上）
        self._alive = True
        #: 有没有 messagebox / askstring 正开着；开着时不做自动刷新，
        #: 否则列表会在对话框底下被重建，删除用的下标就对不上了。
        self._modal_active = False
        #: 账号列表 + 当前账户的快照，用来判断外部（登录窗口）有没有改过账号
        self._signature: tuple = ()
        self._list_signature: tuple = ()
        self._watch_id: str | None = None
        #: 皮肤缓存：key -> PNG 字节（None 表示查过但没有皮肤）；
        #: 以及正在等结果的头像控件
        self._avatar_done: dict[str, bytes | None] = {}
        self._avatar_waiters: dict[str, list[tk.Canvas]] = {}

        self._build()
        self.refresh()
        self.bind("<Destroy>", self._on_destroy, add="+")
        self._watch_id = self.after(800, self._watch)

    # ------------------------------------------------------------ 布局

    def _build(self) -> None:
        root = tk.Frame(self, bg=BG)
        root.pack(fill="both", expand=True, pady=(8, 0))

        # 标题 + 右侧账号数
        head = tk.Frame(root, bg=BG)
        head.pack(fill="x")
        tk.Label(head, text="账户", bg=BG, fg=FG,
                 font=self.app.fonts["h1"]).pack(side="left")
        self._count_label = tk.Label(head, text="", bg=BG, fg=FG_FAINT,
                                     font=self.app.fonts["small"])
        self._count_label.pack(side="right", pady=(8, 0))

        tk.Label(root, text="点一行即可切换为当前账户。", bg=BG, fg=FG_DIM,
                 font=self.app.fonts["small"], anchor="w").pack(fill="x", pady=(4, 10))

        # 底部按钮先 pack（side="bottom"），保证它一定能拿到高度，
        # 否则上面列表的 expand 会把空间吃光、按钮被挤出可视区。
        bottom = tk.Frame(root, bg=BG)
        bottom.pack(side="bottom", fill="x", pady=(12, 0))

        self._ms_btn = FlatButton(bottom, "微软正版登录", command=self._ms_login,
                                  kind="primary", height=36, width=136, bg=BG)
        self._ms_btn.pack(side="left")
        self._skin_btn = FlatButton(bottom, "第三方皮肤站登录", command=self._skin_login,
                                    kind="primary", height=36, width=152, bg=BG)
        self._skin_btn.pack(side="left", padx=(8, 0))
        self._add_btn = FlatButton(bottom, "添加离线账号", command=self._add_offline,
                                   kind="normal", height=36, width=118, bg=BG)
        self._add_btn.pack(side="left", padx=(8, 0))
        self._skin_mgr_btn = FlatButton(bottom, "皮肤管理", command=self._skin_manager,
                                        kind="ghost", height=36, width=104, bg=BG)
        self._skin_mgr_btn.pack(side="right")

        # 列表卡片
        holder = tk.Frame(root, bg=BG_ALT, highlightthickness=1,
                          highlightbackground=BORDER)
        holder.pack(fill="both", expand=True)
        self._scroll = ScrollFrame(holder, bg=BG_ALT)
        self._scroll.pack(fill="both", expand=True, padx=1, pady=1)

    # ------------------------------------------------------------ 对外接口

    def refresh(self) -> None:
        """按 ``app.accounts`` 重建列表（外部改过账号后调用）。"""
        scroll = getattr(self, "_scroll", None)
        if scroll is None:
            return
        try:
            for w in scroll.inner.winfo_children():
                w.destroy()
        except tk.TclError:
            return

        items = list(self.app.accounts)
        try:
            self._count_label.configure(
                text=f"共 {len(items)} 个账号" if items else "还没有账号")
        except tk.TclError:
            pass

        cur = self.app.current_account()
        if not items:
            self._empty()
            self._mark()
            return

        for i, acc in enumerate(items):
            active = cur is not None and acc.uuid == cur.uuid and acc.kind == cur.kind
            self._row(i, acc, active)
            if i != len(items) - 1:
                # 分割线放在行与行之间（行的兄弟节点），
                # SelectableRow 换底色时不会把它一起刷掉。
                tk.Frame(scroll.inner, bg=BORDER, height=1).pack(fill="x")
        self._mark()

    def _mark(self) -> None:
        """刷新完成后记下快照，供 ``_watch`` 比对。"""
        try:
            self._signature = self._snapshot()
            self._list_signature = self._list_key()
        except Exception:                            # noqa: BLE001
            self._signature = ()
            self._list_signature = ()

    # ------------------------------------------------------------ 列表

    def _empty(self) -> None:
        """空列表提示：说明什么都不用做也能玩。"""
        box = tk.Frame(self._scroll.inner, bg=BG_ALT)
        box.pack(fill="x", pady=44)
        inner = tk.Frame(box, bg=BG_ALT)
        inner.pack()
        tk.Label(inner, text="还没有添加账户", bg=BG_ALT, fg=FG_DIM,
                 font=self.app.fonts["h2"]).pack()
        tip = tk.Frame(inner, bg=BG_HOVER)
        tip.pack(pady=(10, 0))
        tk.Label(tip, text="不登录也能玩，启动时会用玩家名做离线登录", bg=BG_HOVER,
                 fg=FG_DIM, font=self.app.fonts["small"]).pack(padx=14, pady=7)

    def _row(self, index: int, acc, active: bool) -> None:
        row = SelectableRow(self._scroll.inner,
                            on_click=lambda i=index: self._switch(i), bg=BG_ALT, pad=8)
        row.pack(fill="x")

        avatar = Avatar(row.inner, size=32, bg=BG_ALT, border=BORDER)
        avatar.pack(side="left", padx=(2, 10))
        self._load_avatar(avatar, acc)

        box = tk.Frame(row.inner, bg=BG_ALT)
        box.pack(side="left", fill="both", expand=True)
        tk.Label(box, text=acc.name, bg=BG_ALT, fg=FG, anchor="w",
                 font=self.app.fonts["body"]).pack(fill="x")
        sub = self._subtitle(acc)
        tk.Label(box, text=sub, bg=BG_ALT, anchor="w",
                 fg=DANGER if acc.expired else (ACCENT if acc.premium else FG_DIM),
                 font=self.app.fonts["small"]).pack(fill="x", pady=(2, 0))

        meta = tk.Frame(row.inner, bg=BG_ALT)
        meta.pack(side="right")

        # 先把点击 / 悬停绑到文字和头像上，**再**创建按钮：
        # attach() 会把 <Button-1> 绑到当时已有的全部子控件，
        # 如果按钮已经存在，点「删除」就会顺带切换账号。
        row.attach()

        FlatButton(meta, "删除", command=lambda i=index, a=acc: self._remove(i, a),
                   kind="ghost", height=24, width=54,
                   font=self.app.fonts["small"], bg=BG_ALT).pack(side="right")
        FlatButton(meta, "复制 UUID", command=lambda a=acc: self._copy_uuid(a),
                   kind="ghost", height=24, width=82,
                   font=self.app.fonts["small"], bg=BG_ALT).pack(side="right", padx=(0, 6))
        if active:
            badge = tk.Label(meta, text="● 当前", bg=BG_ALT, fg=SUCCESS,
                             font=self.app.fonts["small"], cursor="hand2")
            badge.pack(side="right", padx=(0, 10))
            # 徽标是在 attach() 之后建的，自己补一次点击，免得点它没反应
            badge.bind("<Button-1>", lambda _e, i=index: self._switch(i))

        # 当前账户整行铺底色，和「当前」徽标一起把选中状态说清楚。
        # 必须等子控件都建好再调，_paint 只处理调用那一刻存在的控件。
        if active:
            row.set_selected(True)

    def _subtitle(self, acc) -> str:
        """名字下面那行说明：账户类型 + 过期提示。"""
        if acc.premium:
            text = "微软正版账户"
        elif acc.third_party:
            text = acc.label or "第三方账户"
        else:
            text = "离线账户"
        if acc.expired:
            text += "（已过期）"
        return text

    # ------------------------------------------------------------ 头像

    def _load_avatar(self, avatar, acc) -> None:
        """先用首字母占位，再后台拉真实皮肤（照搬 ``app._load_avatar`` 的流程）。"""
        avatar.draw_letter(acc.name)
        uuid = (acc.uuid or "").replace("-", "")
        if not uuid:
            return
        api = acc.api if acc.third_party else ""
        key = f"{api}|{uuid}"

        # 已经问过这个账号的皮肤了（拿到或没拿到都算）：直接复用结果。
        # 面板每点一下都要重建列表，没有这层缓存会对着同一个地址反复发请求。
        if key in self._avatar_done:
            self._paint_skin(avatar, self._avatar_done[key])
            return

        waiters = self._avatar_waiters.get(key)
        if waiters is not None:
            # 同一个账号正在下载，结果回来时一起画
            waiters.append(avatar)
            return
        self._avatar_waiters[key] = [avatar]
        threading.Thread(target=self._fetch_avatar, args=(key, uuid, api),
                         daemon=True).start()

    def _fetch_avatar(self, key: str, uuid: str, api: str) -> None:
        """工作线程：只做网络请求，界面一律交给主线程。"""
        from .. import skins

        try:
            png = skins.fetch_skin_png(uuid, api)
        except Exception:                            # noqa: BLE001
            png = None
        self.app.post(lambda: self._deliver_avatar(key, png))

    def _deliver_avatar(self, key: str, png: bytes | None) -> None:
        """主线程：把拿到的皮肤画到所有等待中的头像上；没拿到就记下来不再重试。"""
        targets = self._avatar_waiters.pop(key, [])
        self._avatar_done[key] = png
        if not png:
            return
        for avatar in targets:
            self._paint_skin(avatar, png)

    def _paint_skin(self, avatar, png: bytes | None) -> None:
        """给一个头像画皮肤图，控件已经没了就安静跳过。"""
        if not png:
            return
        try:
            if not avatar.winfo_exists():
                return
            avatar.draw_skin(png)
        except tk.TclError:
            pass

    # ------------------------------------------------------------ 操作

    def _switch(self, index: int) -> None:
        """点一行：切到当前账户。"""
        items = self.app.accounts
        if not (0 <= index < len(items)):
            return
        acc = items[index]
        self.app.switch_account(index)
        self.refresh()
        self._log(f"已切换到 {acc.name}")

    def _copy_uuid(self, acc) -> None:
        uuid = acc.short_uuid()
        if not uuid:
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(uuid)
            self.update_idletasks()
        except tk.TclError:
            return
        self._log(f"已复制 UUID：{uuid}")

    def _remove(self, index: int, acc) -> None:
        """删除一个账号，先确认。下标可能已经过期，所以按对象重新定位。"""
        items = self.app.accounts
        if not (0 <= index < len(items)) or items[index] is not acc:
            index = self._find(acc)
            if index < 0:
                self.refresh()
                return
        self._modal_active = True
        try:
            ok = messagebox.askyesno("删除账号", f"确定要删除账号「{acc.name}」吗？",
                                     parent=self)
        finally:
            self._modal_active = False
        if not ok:
            return
        self.app.remove_account(index)
        self.refresh()
        self._log(f"已删除账号 {acc.name}")

    def _find(self, acc) -> int:
        """在账号列表里按「同一个对象 / 同 kind+uuid+名字」找下标，找不到返回 -1。"""
        for i, item in enumerate(self.app.accounts):
            if item is acc:
                return i
            if (item.kind == acc.kind and item.uuid == acc.uuid
                    and item.name == acc.name):
                return i
        return -1

    def _add_offline(self) -> None:
        """添加离线账号：弹一个输入框，校验玩家名。"""
        self._modal_active = True
        try:
            name = simpledialog.askstring("添加离线账号", "输入玩家名：", parent=self,
                                          initialvalue="Steve")
        finally:
            self._modal_active = False
        if name is None:
            return
        name = name.strip()
        if not NAME_PATTERN.match(name):
            messagebox.showwarning("玩家名不合法",
                                   "玩家名需要 3–16 个字符，只能包含字母、数字和下划线。",
                                   parent=self)
            return
        acc = self.app.add_offline_account(name)
        self.refresh()
        self._log(f"已添加离线账号 {acc.name}")

    def _ms_login(self) -> None:
        self.app.open_login()
        self._log("已打开微软正版登录窗口")

    def _skin_login(self) -> None:
        self.app.open_skin_login()
        self._log("已打开第三方皮肤站登录窗口")

    def _skin_manager(self) -> None:
        self.app.open_skin_manager()

    # ------------------------------------------------------------ 同步

    def _snapshot(self) -> tuple:
        """账号列表 + 当前账户的快照，用来发现外部改动。"""
        cur = self.app.current_account()
        return (
            self._list_key(),
            (cur.kind, cur.name, cur.uuid) if cur is not None else None,
        )

    def _list_key(self) -> tuple:
        """只反映「有哪些账号」的部分，切换当前账户时不变。"""
        return tuple((a.kind, a.name, a.uuid) for a in self.app.accounts)

    def _watch(self) -> None:
        """定时对一下快照：登录窗口改了账号就自动重画（不碰正在弹的对话框）。"""
        self._watch_id = None
        if not self._alive:
            return
        if not self._modal_active:
            try:
                if self._snapshot() != self._signature:
                    # 账号增删了（多半是登录窗口干的），皮肤缓存可能不再适用
                    if self._list_key() != self._list_signature:
                        self._avatar_done.clear()
                    self.refresh()
            except Exception:                        # noqa: BLE001
                pass
        if self._alive:
            try:
                self._watch_id = self.after(800, self._watch)
            except tk.TclError:
                self._watch_id = None

    def _on_destroy(self, event) -> None:
        if event.widget is not self:
            return
        self._alive = False
        if self._watch_id is not None:
            try:
                self.after_cancel(self._watch_id)
            except tk.TclError:
                pass
            self._watch_id = None

    # ------------------------------------------------------------ 内部

    def _log(self, message: str) -> None:
        """写父级日志（回调可能来自别的线程，所以这里自己吞掉异常）。"""
        if self._on_log is None:
            return
        try:
            self._on_log(message)
        except Exception:                            # noqa: BLE001
            pass
