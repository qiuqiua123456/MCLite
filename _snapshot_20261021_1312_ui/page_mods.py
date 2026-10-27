"""Mod 管理页：列出 mods 目录、启用/禁用、删除、导入、打开目录。"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from ..mods import delete_mod, import_mods, list_mods, mods_dir, open_folder, toggle_mod
from . import images
from .theme import (
    ACCENT, BG, BG_ALT, BG_HOVER, BORDER, DANGER, FG, FG_DIM, FG_FAINT,
    SUCCESS, WARN, FlatButton, ScrollFrame,
)
from .widgets import Page, Select, SelectableRow

#: 下拉框里代表「所有版本共用的那个 mods 目录」
SHARED_LABEL = "（共用目录）"


class ModsPage(Page):
    title = "Mod"

    def build(self) -> None:
        self._entries = []
        self._selected = None
        self._rows: dict[str, SelectableRow] = {}
        self._versions: list[str] = []

        root = tk.Frame(self, bg=BG)
        root.pack(fill="both", expand=True, padx=24, pady=(20, 12))

        head = tk.Frame(root, bg=BG)
        head.pack(fill="x")
        tk.Label(head, text="Mod 管理", bg=BG, fg=FG,
                 font=self.app.fonts["h1"]).pack(side="left")
        self._path_label = tk.Label(head, text="", bg=BG, fg=FG_FAINT,
                                    font=self.app.fonts["small"])
        self._path_label.pack(side="right", pady=(8, 0))

        # 实例选择行
        inst = tk.Frame(root, bg=BG)
        inst.pack(fill="x", pady=(10, 0))
        tk.Label(inst, text="当前实例", bg=BG, fg=FG_DIM,
                 font=self.app.fonts["small"]).pack(side="left")
        self._select = Select(inst, values=[SHARED_LABEL], value=SHARED_LABEL,
                              on_change=lambda _v: self.reload(), width=34, height=30,
                              bg=BG_ALT)
        self._select.pack(side="left", padx=(8, 0))
        self._select.configure(width=260)
        self._inst_hint = tk.Label(inst, text="", bg=BG, fg=FG_FAINT,
                                   font=self.app.fonts["small"])
        self._inst_hint.pack(side="left", padx=(10, 0))

        tools = tk.Frame(root, bg=BG)
        tools.pack(fill="x", pady=(10, 10))
        FlatButton(tools, "Modrinth 下载", command=self.open_download_dialog,
                   kind="primary", height=30, width=112,
                   bg=BG).pack(side="left")
        FlatButton(tools, "安装整合包…", command=self.open_pack_market, kind="normal",
                   height=30, width=94, bg=BG).pack(side="left", padx=(8, 0))
        FlatButton(tools, "导出整合包…", command=self.export_pack, kind="normal",
                   height=30, width=94, bg=BG).pack(side="left", padx=(8, 0))
        FlatButton(tools, "导入本地 Mod…", command=self.import_dialog, kind="normal",
                   height=30, width=104, bg=BG).pack(side="left", padx=8)
        FlatButton(tools, "刷新", command=self.reload, kind="ghost", height=30,
                   width=52, bg=BG).pack(side="left")
        FlatButton(tools, "打开 mods 目录", command=self.open_dir, kind="ghost",
                   height=30, width=110, bg=BG).pack(side="left", padx=8)
        self._count_label = tk.Label(tools, text="", bg=BG, fg=FG_FAINT,
                                     font=self.app.fonts["small"])
        self._count_label.pack(side="right", pady=(6, 0))

        # 列表
        card = tk.Frame(root, bg=BG_ALT)
        card.pack(fill="both", expand=True)

        header = tk.Frame(card, bg=BG_ALT, height=32)
        header.pack(fill="x")
        header.pack_propagate(False)
        for text, width in (("名称", 0), ("大小", 90), ("状态", 90), ("", 0)):
            if width:
                tk.Label(header, text=text, bg=BG_ALT, fg=FG_FAINT, width=10,
                         anchor="e", font=self.app.fonts["small"]).pack(side="right", padx=(0, 8), pady=8)
            else:
                tk.Label(header, text=text, bg=BG_ALT, fg=FG_FAINT,
                         anchor="w", font=self.app.fonts["small"]).pack(side="left", padx=12, pady=8)
            if text == "名称":
                pass
        tk.Frame(card, bg=BORDER, height=1).pack(fill="x")

        self._scroll = ScrollFrame(card, bg=BG_ALT)
        self._scroll.pack(fill="both", expand=True)

        # 底部操作
        bottom = tk.Frame(root, bg=BG)
        bottom.pack(fill="x", pady=(10, 0))
        self._toggle_btn = FlatButton(bottom, "启用 / 禁用", command=self.toggle_selected,
                                      kind="primary", height=34, width=120, bg=BG)
        self._toggle_btn.pack(side="left")
        self._delete_btn = FlatButton(bottom, "删除", command=self.delete_selected,
                                      kind="danger", height=34, width=80, bg=BG)
        self._delete_btn.pack(side="left", padx=8)
        self._toggle_btn.set_enabled(False)
        self._delete_btn.set_enabled(False)

        self.after(150, self.reload)

    # ------------------------------------------------------------ 实例

    def _separate(self) -> bool:
        from .. import instances, modpack
        game_dir = self.app.cfg.game_dir
        vid = self._select.get()
        if not vid or vid == SHARED_LABEL:
            return False
        return instances.effective(
            game_dir, vid,
            bool(self.app.cfg.get("separate_instances", False)) or modpack.is_pack(game_dir, vid))

    def _base(self) -> Path:
        """当前实例对应的「基础目录」，mods 就放在它下面。"""
        from .. import instances
        game_dir = self.app.cfg.game_dir
        vid = self._select.get()
        if vid and vid != SHARED_LABEL and self._separate():
            return instances.instance_dir(game_dir, vid)
        return game_dir

    def _sync_versions(self) -> None:
        from ..launcher import list_installed_versions
        try:
            versions = list_installed_versions(self.app.cfg.game_dir)
        except Exception:                            # noqa: BLE001
            versions = []
        self._versions = versions
        values = [SHARED_LABEL] + versions
        self._select.set_values(values)
        cur = self._select.get()
        if cur and cur not in values:
            home = getattr(self.app, "_pages", {}).get("home")
            sel = getattr(home, "_selected", "") if home is not None else ""
            self._select.set(sel if sel in versions else SHARED_LABEL)

    # ------------------------------------------------------------ 数据

    def on_show(self) -> None:
        self._sync_versions()
        self.reload()

    def reload(self) -> None:
        for w in self._scroll.inner.winfo_children():
            w.destroy()
        self._rows.clear()
        base = self._base()
        self._entries = list_mods(base)
        self._selected = None
        self._toggle_btn.set_enabled(False)
        self._delete_btn.set_enabled(False)

        d = mods_dir(base)
        self._path_label.configure(text=str(d))
        if base != self.app.cfg.game_dir:
            self._inst_hint.configure(text="已隔离：只影响这个版本", fg=ACCENT)
        else:
            self._inst_hint.configure(text="所有版本共用", fg=FG_FAINT)
        enabled = sum(1 for m in self._entries if m.enabled)
        self._count_label.configure(
            text=f"{len(self._entries)} 个 · 启用 {enabled}")

        if not self._entries:
            box = tk.Frame(self._scroll.inner, bg=BG_ALT)
            box.pack(fill="x", pady=26)
            art = images.load(self, "empty-mods")
            if art is not None:
                cap = tk.Label(box, image=art, bg=BG_ALT, bd=0)
                cap.image = art
                cap.pack()
            tk.Label(box, text="mods 目录是空的", bg=BG_ALT, fg=FG_DIM,
                     font=self.app.fonts["body"]).pack(pady=(10, 0))
            tk.Label(box, text=f"{d}", bg=BG_ALT, fg=FG_FAINT,
                     font=self.app.fonts["small"]).pack(pady=(4, 0))
            return

        for entry in self._entries:
            self._add_row(entry)

    def _add_row(self, entry) -> None:
        row = SelectableRow(self._scroll.inner,
                            on_click=lambda e=entry: self._pick_row(e), bg=BG_ALT, pad=8)
        row.pack(fill="x")

        color = ACCENT if entry.enabled else FG_FAINT
        stripe = tk.Frame(row.inner, bg=color, width=3, height=28)
        stripe.pack(side="left", fill="y", padx=(0, 10))

        box = tk.Frame(row.inner, bg=BG_ALT)
        box.pack(side="left", fill="both", expand=True)
        tk.Label(box, text=entry.name, bg=BG_ALT, fg=FG, anchor="w",
                 font=self.app.fonts["body"]).pack(fill="x")

        meta = tk.Frame(row.inner, bg=BG_ALT)
        meta.pack(side="right")

        tk.Label(meta, text=entry.size_text, bg=BG_ALT, fg=FG_DIM, width=9,
                 anchor="e", font=self.app.fonts["small"]).pack(side="left", padx=(0, 12))
        state = "已启用" if entry.enabled else "已禁用"
        tk.Label(meta, text=state, bg=BG_ALT, fg=SUCCESS if entry.enabled else FG_FAINT,
                 width=7, anchor="w", font=self.app.fonts["small"]).pack(side="left")

        row.attach()
        self._rows[entry.name] = row

    def _pick_row(self, entry) -> None:
        self._selected = entry
        for k, row in self._rows.items():
            row.set_selected(k == entry.name)
        self._toggle_btn.set_enabled(True)
        self._delete_btn.set_enabled(True)
        self._toggle_btn.set_text("禁用" if entry.enabled else "启用")

    # ------------------------------------------------------------ 操作

    def toggle_selected(self) -> None:
        if not self._selected:
            return
        ok, msg = toggle_mod(self._selected)
        if ok:
            self.app.notify(msg, "ok")
            self.reload()
        else:
            self.app.notify(msg, "err")

    def delete_selected(self) -> None:
        if not self._selected:
            return
        name = self._selected.name
        if not messagebox.askyesno("确认删除", f"确定要删除这个 Mod 吗？\n\n{name}",
                                   parent=self):
            return
        ok, msg = delete_mod(self._selected)
        if ok:
            self.app.notify(f"已删除 {name}", "ok")
            self.reload()
        else:
            messagebox.showerror("删除失败", msg, parent=self)

    def import_dialog(self) -> None:
        files = filedialog.askopenfilenames(
            parent=self, title="选择要导入的 Mod",
            filetypes=[("Mod 文件", "*.jar"), ("所有文件", "*.*")])
        if not files:
            return
        ok, errors = import_mods(self._base(), [Path(f) for f in files])
        if ok:
            self.app.notify(f"已导入 {ok} 个 Mod", "ok")
        if errors:
            messagebox.showwarning("部分未导入", "\n".join(errors[:10]), parent=self)
        self.reload()

    def open_dir(self) -> None:
        open_folder(mods_dir(self._base()))

    def handle_drop(self, paths) -> None:
        """拖入文件：.jar 直接当 Mod 装，压缩包交给整合包安装流程。"""
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
            ok, errors = import_mods(self._base(), jars)
            if ok:
                self.app.notify(f"已导入 {ok} 个 Mod", "ok")
            if errors:
                messagebox.showwarning("部分未导入", "\n".join(errors[:10]), parent=self)
            self.reload()
        if packs:
            from .pack_dialog import PackInstallDialog
            home = getattr(self.app, "_pages", {}).get("home")
            dlg = PackInstallDialog(self.app, packs[0], on_done=self._on_pack_done,
                                    base_version=str(getattr(home, "_selected", "") or ""))
            try:
                dlg.grab_set()
            except tk.TclError:
                pass
        if other and not jars and not packs:
            self.app.notify("只支持拖入 .jar / .mrpack / .zip", "warn")

    def open_pack_market(self) -> None:
        from .pack_dialog import PackMarketDialog
        dlg = PackMarketDialog(self.app, on_done=self._on_pack_done)
        try:
            dlg.grab_set()
        except tk.TclError:
            pass

    def export_pack(self) -> None:
        """把当前实例导出成 .mrpack。"""
        from .. import exportpack

        version = self._select.get()
        if version == SHARED_LABEL:
            home = getattr(self.app, "_pages", {}).get("home")
            version = str(getattr(home, "_selected", "") or "")
        if not version:
            messagebox.showinfo("导出整合包",
                                "先在「开始」页选中一个版本，或在上面选一个实例版本。",
                                parent=self)
            return
        target = filedialog.asksaveasfilename(
            parent=self, title="导出整合包", defaultextension=".mrpack",
            initialfile=f"{version}.mrpack", initialdir=str(Path.home() / "Desktop"),
            filetypes=[("Modrinth 整合包", "*.mrpack"), ("所有文件", "*.*")])
        if not target:
            return
        self.app.set_status("正在导出整合包…")
        game_dir = self.app.cfg.game_dir

        def work() -> None:
            try:
                res = exportpack.export_pack(
                    game_dir, version, Path(target),
                    on_log=lambda m: self.app.post(lambda mm=m: self.app.set_status(mm[:60])))
            except Exception as exc:                 # noqa: BLE001
                msg = str(exc)
                self.app.post(lambda: self.app.notify(f"导出失败：{msg}", "err"))
                self.app.post(lambda: self.app.set_status("就绪"))
                return
            text = res.summary()
            self.app.post(lambda: self.app.notify(text, "ok"))
            self.app.post(lambda: self.app.set_status("就绪"))

        import threading
        threading.Thread(target=work, daemon=True).start()

    def _on_pack_done(self, vid: str) -> None:
        self.app.notify(f"整合包已安装：{vid}", "ok")
        home = getattr(self.app, "_pages", {}).get("home")
        if home is not None:
            home.reload_versions()
            try:
                home._select(vid)
            except Exception:                        # noqa: BLE001
                pass
        self._sync_versions()
        self._select.set(vid)
        self.reload()

    def open_download_dialog(self) -> None:
        from .. import modrinth
        from .mod_dialog import ModDownloadDialog
        version = ""
        home = getattr(self.app, "_pages", {}).get("home")
        if home is not None:
            version = getattr(home, "_selected", "") or ""
        loader = modrinth.detect_loader(self.app.cfg.game_dir, version) if version else ""
        dlg = ModDownloadDialog(self.app, game_version=version, loader=loader,
                                target=self._base())
        dlg.grab_set()
        self.wait_window(dlg)
        self.reload()
