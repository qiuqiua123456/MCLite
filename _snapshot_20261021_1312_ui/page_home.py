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
from . import images
from .theme import (
    ACCENT, BG, BG_ALT, BG_HOVER, BORDER, DANGER, FG, FG_DIM, FG_FAINT,
    SUCCESS, WARN, FlatButton, ScrollFrame, Slider, round_rect,
)
from .widgets import LogPanel, Page, ProgressBar, SelectableRow


class HomePage(Page):
    title = "开始"

    def build(self) -> None:
        self._selected: str | None = None
        self._rows: dict[str, SelectableRow] = {}
        self._proc = None
        self._launching = False
        self._tail_stop: threading.Event | None = None

        root = tk.Frame(self, bg=BG)
        root.pack(fill="both", expand=True, padx=24, pady=(20, 12))

        # ---------------- 顶部主视觉（ComfyUI 出的浮岛插画，文字压在左侧深蓝上）
        head = tk.Frame(root, bg=BG)
        head.pack(fill="x")
        hero = images.load(self, "hero")
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
        else:
            tk.Label(head, text="启动 Minecraft", bg=BG, fg=FG,
                     font=self.app.fonts["h1"]).pack(side="left")
        self._dir_label = tk.Label(head, text="", bg=BG, fg=FG_FAINT,
                                   font=self.app.fonts["small"])
        self._dir_label.pack(side="right", pady=(8, 0), anchor="n")

        # ---------------- 主体：左右分栏
        body = tk.Frame(root, bg=BG)
        body.pack(fill="both", expand=True, pady=(14, 0))

        # 左：版本列表
        left = tk.Frame(body, bg=BG_ALT, width=380)
        left.pack(side="left", fill="both", expand=False)
        left.pack_propagate(False)

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

        self._scroll = ScrollFrame(left, bg=BG_ALT)
        self._scroll.pack(fill="both", expand=True)

        tk.Frame(left, bg=BORDER, height=1).pack(fill="x")
        tk.Label(left, text="把 .jar / .zip / .mrpack 拖进窗口即可安装",
                 bg=BG_ALT, fg=FG_FAINT, font=self.app.fonts["small"],
                 anchor="w", padx=14, pady=8).pack(fill="x")

        # 右：启动面板
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(18, 0))

        panel = tk.Frame(right, bg=BG_ALT)
        panel.pack(fill="x")

        info = tk.Frame(panel, bg=BG_ALT, padx=18, pady=16)
        info.pack(fill="x")

        self._big_name = tk.Label(info, text="未选择版本", bg=BG_ALT, fg=FG,
                                  font=("Segoe UI", 20, "bold"), anchor="w")
        self._big_name.pack(fill="x")
        self._big_sub = tk.Label(info, text="从左侧选择一个版本", bg=BG_ALT, fg=FG_DIM,
                                 font=self.app.fonts["small"], anchor="w")
        self._big_sub.pack(fill="x", pady=(4, 0))

        tk.Frame(panel, bg=BORDER, height=1).pack(fill="x", padx=18)

        opts = tk.Frame(panel, bg=BG_ALT, padx=18, pady=14)
        opts.pack(fill="x")

        row1 = tk.Frame(opts, bg=BG_ALT)
        row1.pack(fill="x", pady=3)
        tk.Label(row1, text="玩家名", bg=BG_ALT, fg=FG_DIM, width=7, anchor="w",
                 font=self.app.fonts["body"]).pack(side="left")
        self._name_var = tk.StringVar(value=self.app.cfg.get("username") or "Steve")
        self._name_entry = tk.Entry(row1, textvariable=self._name_var, bg=BG, fg=FG,
                                    insertbackground=FG, bd=0, highlightthickness=1,
                                    highlightbackground=BORDER, highlightcolor=ACCENT,
                                    disabledbackground=BG, disabledforeground=FG_DIM,
                                    font=self.app.fonts["body"])
        self._name_entry.pack(side="left", fill="x", expand=True, ipady=4)
        self._name_entry.bind("<FocusOut>", self._on_name_change)
        self._login_btn = FlatButton(row1, "账号管理", command=self.app.open_accounts,
                                     kind="ghost", height=26, width=78,
                                     font=self.app.fonts["small"], bg=BG_ALT)
        self._login_btn.pack(side="right", padx=(8, 0))

        row2 = tk.Frame(opts, bg=BG_ALT)
        row2.pack(fill="x", pady=3)
        tk.Label(row2, text="Java", bg=BG_ALT, fg=FG_DIM, width=7, anchor="w",
                 font=self.app.fonts["body"]).pack(side="left")
        self._java_label = tk.Label(row2, text="检测中…", bg=BG_ALT, fg=FG_DIM,
                                    font=self.app.fonts["small"], anchor="w")
        self._java_label.pack(side="left", fill="x", expand=True)
        FlatButton(row2, "重新检测", command=self._refresh_java, kind="ghost",
                   height=24, font=self.app.fonts["small"], bg=BG_ALT).pack(side="right")

        row3 = tk.Frame(opts, bg=BG_ALT)
        row3.pack(fill="x", pady=3)
        tk.Label(row3, text="内存", bg=BG_ALT, fg=FG_DIM, width=7, anchor="w",
                 font=self.app.fonts["body"]).pack(side="left")
        self._mem_var = tk.IntVar(value=int(self.app.cfg.get("memory_mb") or 4096))
        self._mem_slider = Slider(row3, 1024, 16384, self._mem_var.get(), step=512,
                                  command=lambda v: self._on_mem_change(v),
                                  width=260, suffix=" MB", bg=BG_ALT)
        self._mem_slider.pack(side="left", fill="x", expand=True)

        # 启动按钮
        actions = tk.Frame(panel, bg=BG_ALT, padx=18, pady=16)
        actions.pack(fill="x")
        self._launch_btn = FlatButton(actions, "启动游戏", command=self.launch,
                                      kind="primary", height=40, width=132,
                                      font=("Microsoft YaHei UI", 11, "bold"), bg=BG_ALT)
        self._launch_btn.pack(side="left")
        FlatButton(actions, "游戏目录", command=self._open_dir, kind="normal",
                   height=40, width=100, bg=BG_ALT).pack(side="left", padx=8)
        self._stop_btn = FlatButton(actions, "结束游戏", command=self._stop_game,
                                    kind="danger", height=40, width=92, bg=BG_ALT)
        self._stop_btn.pack(side="left", padx=0)
        self._stop_btn.set_enabled(False)

        # 实例管理
        manage = tk.Frame(right, bg=BG_ALT, padx=18, pady=0)
        manage.pack(fill="x")
        self._delete_btn = FlatButton(manage, "删除版本", command=self._delete_version,
                                      kind="danger", height=28, width=90,
                                      font=self.app.fonts["small"], bg=BG_ALT)
        self._delete_btn.pack(side="left", pady=(0, 12))
        self._delete_btn.set_enabled(False)
        self._world_btn = FlatButton(manage, "存档", command=self._open_worlds,
                                     kind="ghost", height=28, width=56,
                                     font=self.app.fonts["small"], bg=BG_ALT)
        self._world_btn.pack(side="left", padx=(8, 0), pady=(0, 12))
        self._verify_btn = FlatButton(manage, "校验", command=self._open_verify,
                                      kind="ghost", height=28, width=56,
                                      font=self.app.fonts["small"], bg=BG_ALT)
        self._verify_btn.pack(side="left", padx=6, pady=(0, 12))
        self._export_btn = FlatButton(manage, "导出", command=self._export_pack,
                                      kind="ghost", height=28, width=56,
                                      font=self.app.fonts["small"], bg=BG_ALT)
        self._export_btn.pack(side="left", padx=6, pady=(0, 12))
        FlatButton(manage, "日志", command=self._open_logs, kind="ghost",
                   height=28, width=56, font=self.app.fonts["small"],
                   bg=BG_ALT).pack(side="left", padx=6, pady=(0, 12))
        for btn in (self._world_btn, self._verify_btn, self._export_btn):
            btn.set_enabled(False)

        # 日志
        log_card = tk.Frame(right, bg=BG_ALT)
        log_card.pack(fill="both", expand=True, pady=(14, 0))
        lb = tk.Frame(log_card, bg=BG_ALT, height=34)
        lb.pack(fill="x")
        lb.pack_propagate(False)
        tk.Label(lb, text="启动日志", bg=BG_ALT, fg=FG_DIM,
                 font=self.app.fonts["small"]).pack(side="left", padx=12, pady=8)
        FlatButton(lb, "清空", command=lambda: self._log.clear(), kind="ghost",
                   height=22, font=self.app.fonts["small"], bg=BG_ALT,
                   width=56).pack(side="right", padx=8, pady=6)
        tk.Frame(log_card, bg=BORDER, height=1).pack(fill="x")
        self._log = LogPanel(log_card, height=8)
        self._log.pack(fill="both", expand=True)

        self._javas = []
        self.after(150, self.reload_versions)
        self.after(300, self._refresh_java)
        self.after(120, self.on_account_changed)

    # ------------------------------------------------------------ 数据

    def on_show(self) -> None:
        self._dir_label.configure(text=str(self.app.cfg.game_dir))
        if not self._rows:
            self.reload_versions()

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
            self._java_label.configure(text=f"{best.label}  （共 {len(javas)} 个）", fg=FG_DIM)

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
        text = f"{pick.label}   需要 Java {need}+   共 {len(self._javas)} 个"
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
            self._login_btn.set_text("切换账号")
        elif acc is not None:
            self._name_entry.configure(state="normal")
            self._name_var.set(acc.name)
            self._login_btn.set_text("账号管理")
        else:
            self._name_entry.configure(state="normal")
            self._name_var.set(self.app.cfg.get("username") or "Steve")
            self._login_btn.set_text("账号管理")

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
