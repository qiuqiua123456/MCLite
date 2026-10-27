"""内嵌式内容管理面板：Mod / 资源包 / 光影 / 数据包。

从 ``page_mods.py`` 的 ``ModsPage`` 移植而来，改成可以贴在开始页里的一个
``tk.Frame``（没有页面标题、没有窗口装饰），并做了一点增强：

1. 顶部多了「内容类型」下拉框，同一套界面管理 mods / resourcepacks /
   shaderpacks / datapacks 四种目录；
2. 下载按钮不再自己弹窗口，通过 ``on_download`` 回调交给父级切换标签页。

启用/禁用的约定和 mods 一致：``NAME`` 表示启用，``NAME.disabled`` 表示禁用。
mods 目录继续复用 ``..mods`` 里的辅助函数（它们已经处理了这个后缀）。
"""

from __future__ import annotations

import shutil
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from ..mods import (
    DISABLED_SUFFIX, ModEntry, delete_mod, import_mods, list_mods, mods_dir,
    open_folder, toggle_mod,
)
from .theme import (
    ACCENT, BG, BG_ALT, BG_HOVER, BORDER, DANGER, FG, FG_DIM, FG_FAINT,
    SUCCESS, WARN, FlatButton, ScrollFrame,
)
from .widgets import Select, SelectableRow

#: 下拉框里代表「所有版本共用的那个目录」
SHARED_LABEL = "（共用目录）"

#: 支持的内容类型：(目录名, 界面上的中文名)，顺序即下拉框顺序
CONTENT_TYPES: tuple[tuple[str, str], ...] = (
    ("mods", "模组"),
    ("resourcepacks", "资源包"),
    ("shaderpacks", "光影"),
    ("datapacks", "数据包"),
)

#: 目录名 -> 中文名
TYPE_LABELS: dict[str, str] = {key: label for key, label in CONTENT_TYPES}

#: 切换到某类内容时，列表上方的一句说明（没有就不显示）
TYPE_HINTS: dict[str, str] = {
    "datapacks": "提示：原版数据包一般放进存档目录的 datapacks 里才生效，这里放的是全局目录。",
    "shaderpacks": "提示：光影需要先装好对应的加载器（Iris / OptiFine 之类）。",
}


# ---------------------------------------------------------------- 非 mods 目录

def _list_files(directory: Path) -> list[ModEntry]:
    """列出目录里的文件，按 ``.disabled`` 后缀判断启用状态。

    mods 目录有专门的 ``list_mods``（只认 ``.jar``），资源包 / 光影 / 数据包
    的扩展名五花八门，所以这里不筛扩展名，只要是文件就列出来。
    """
    if not directory.is_dir():
        return []
    out: list[ModEntry] = []
    try:
        for p in directory.iterdir():
            if not p.is_file() or p.name.startswith("."):
                continue
            if p.name.lower().endswith(DISABLED_SUFFIX):
                display = p.name[: -len(DISABLED_SUFFIX)]
                enabled = False
            else:
                display = p.name
                enabled = True
            if not display:
                continue
            try:
                size = p.stat().st_size
            except OSError:
                size = 0
            out.append(ModEntry(name=display, path=p, size=size, enabled=enabled))
    except OSError:
        return []
    out.sort(key=lambda m: m.name.lower())
    return out


def _toggle_file(entry: ModEntry) -> tuple[bool, str]:
    """切换启用状态（重命名加/去 ``.disabled``），返回 (成功, 说明)。"""
    src = entry.path
    if entry.enabled:
        dst = src.with_name(src.name + DISABLED_SUFFIX)
    else:
        if not src.name.lower().endswith(DISABLED_SUFFIX):
            return False, "文件名异常"
        dst = src.with_name(src.name[: -len(DISABLED_SUFFIX)])
    if dst.exists():
        return False, f"目标已存在：{dst.name}"
    try:
        src.rename(dst)
    except OSError as exc:
        return False, f"重命名失败：{exc}"
    return True, "已禁用" if entry.enabled else "已启用"


def _delete_file(entry: ModEntry) -> tuple[bool, str]:
    """删除一个文件，返回 (成功, 说明)。"""
    try:
        entry.path.unlink()
    except OSError as exc:
        return False, f"删除失败：{exc}"
    return True, "已删除"


def _import_files(directory: Path, files: list[Path]) -> tuple[int, list[str]]:
    """把文件复制进目录，返回 (成功数, 错误列表)。同名文件跳过。"""
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return 0, [f"无法创建目录：{exc}"]
    ok = 0
    errors: list[str] = []
    for f in files:
        try:
            target = directory / f.name
            if target.exists():
                errors.append(f"已存在，跳过：{f.name}")
                continue
            shutil.copy2(f, target)
            ok += 1
        except OSError as exc:
            errors.append(f"{f.name}: {exc}")
    return ok, errors


# ---------------------------------------------------------------- 面板

class ModsPanel(tk.Frame):
    """内嵌的内容管理面板，可在开始页里当标签页使用。"""

    def __init__(self, master, app, on_log=None, on_download=None):
        super().__init__(master, bg=BG)
        self.app = app
        #: 日志回调（可空），用来把「导入了几个文件」之类的信息写到父级日志
        self._on_log = on_log
        #: 点击「下载」时通知父级切到下载标签页，参数是当前内容类型
        self._on_download = on_download
        #: 当前内容类型（目录名）
        self._type: str = "mods"
        #: set_version 传进来的游戏目录；None 表示跟着 app.cfg.game_dir 走
        self._game_dir: Path | None = None
        self._entries: list[ModEntry] = []
        self._selected: ModEntry | None = None
        self._rows: dict[str, SelectableRow] = {}
        self._versions: list[str] = []
        #: 上次 rebuild 的内容签名，用来跳过没有变化的重复重建
        self._sig: tuple | None = None
        self._sig_type: str | None = None

        self._build()
        self._sync_versions()
        self.reload()

    # ------------------------------------------------------------ 界面

    def _build(self) -> None:
        root = tk.Frame(self, bg=BG)
        root.pack(fill="both", expand=True, pady=(8, 0))

        # 第一行：内容类型 + 实例选择 + 当前路径
        bar = tk.Frame(root, bg=BG)
        bar.pack(fill="x")
        tk.Label(bar, text="内容", bg=BG, fg=FG_DIM,
                 font=self.app.fonts["small"]).pack(side="left")
        type_labels = [label for _key, label in CONTENT_TYPES]
        self._type_select = Select(bar, values=type_labels, value=type_labels[0],
                                   on_change=self._on_type_change, width=8,
                                   height=30, bg=BG_ALT)
        self._type_select.pack(side="left", padx=(8, 0))
        self._type_select.configure(width=104)

        tk.Label(bar, text="当前实例", bg=BG, fg=FG_DIM,
                 font=self.app.fonts["small"]).pack(side="left", padx=(18, 0))
        self._select = Select(bar, values=[SHARED_LABEL], value=SHARED_LABEL,
                              on_change=lambda _v: self.reload(), width=34,
                              height=30, bg=BG_ALT)
        self._select.pack(side="left", padx=(8, 0))
        self._select.configure(width=220)

        self._inst_hint = tk.Label(bar, text="", bg=BG, fg=FG_FAINT,
                                   font=self.app.fonts["small"])
        self._inst_hint.pack(side="left", padx=(10, 0))

        self._path_label = tk.Label(bar, text="", bg=BG, fg=FG_FAINT,
                                    font=self.app.fonts["small"])
        self._path_label.pack(side="right", pady=(6, 0))

        # 第二行：工具条
        tools = tk.Frame(root, bg=BG)
        tools.pack(fill="x", pady=(10, 10))
        FlatButton(tools, "下载", command=self.open_download, kind="primary",
                   height=30, width=72, bg=BG).pack(side="left")
        FlatButton(tools, "导入…", command=self.import_dialog, kind="normal",
                   height=30, width=80, bg=BG).pack(side="left", padx=(8, 0))
        FlatButton(tools, "刷新", command=self.refresh, kind="ghost", height=30,
                   width=52, bg=BG).pack(side="left", padx=(8, 0))
        FlatButton(tools, "打开目录", command=self.open_dir, kind="ghost",
                   height=30, width=88, bg=BG).pack(side="left", padx=(8, 0))
        self._count_label = tk.Label(tools, text="", bg=BG, fg=FG_FAINT,
                                     font=self.app.fonts["small"])
        self._count_label.pack(side="right", pady=(6, 0))

        # 类型说明（按需显示）
        self._type_hint = tk.Label(root, text="", bg=BG, fg=WARN,
                                   font=self.app.fonts["small"], anchor="w")

        # 列表卡片
        card = tk.Frame(root, bg=BG_ALT)
        card.pack(fill="both", expand=True)
        self._card = card

        header = tk.Frame(card, bg=BG_ALT, height=32)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="名称", bg=BG_ALT, fg=FG_FAINT, anchor="w",
                 font=self.app.fonts["small"]).pack(side="left", padx=12, pady=8)
        tk.Label(header, text="状态", bg=BG_ALT, fg=FG_FAINT, width=7,
                 anchor="w", font=self.app.fonts["small"]).pack(
                     side="right", padx=(0, 12), pady=8)
        tk.Label(header, text="大小", bg=BG_ALT, fg=FG_FAINT, width=9,
                 anchor="e", font=self.app.fonts["small"]).pack(
                     side="right", padx=(0, 12), pady=8)
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

    # ------------------------------------------------------------ 实例

    def _game(self) -> Path:
        """当前的游戏目录（可能被 ``set_version`` 覆盖过）。"""
        if self._game_dir is not None:
            return Path(self._game_dir)
        return Path(self.app.cfg.game_dir)

    def _separate(self) -> bool:
        from .. import instances, modpack
        game_dir = self._game()
        vid = self._select.get()
        if not vid or vid == SHARED_LABEL:
            return False
        return instances.effective(
            game_dir, vid,
            bool(self.app.cfg.get("separate_instances", False)) or modpack.is_pack(game_dir, vid))

    def _base(self) -> Path:
        """当前实例对应的「基础目录」，各种内容目录就放在它下面。"""
        from .. import instances
        game_dir = self._game()
        vid = self._select.get()
        if vid and vid != SHARED_LABEL and self._separate():
            return instances.instance_dir(game_dir, vid)
        return game_dir

    def _dir_for(self, base: Path) -> Path:
        """某个基础目录下、当前内容类型对应的目录。"""
        if self._type == "mods":
            return mods_dir(base)
        return Path(base) / self._type

    def _dir(self) -> Path:
        return self._dir_for(self._base())

    def _sync_versions(self) -> None:
        from ..launcher import list_installed_versions
        try:
            versions = list_installed_versions(self._game())
        except Exception:                            # noqa: BLE001
            versions = []
        self._versions = versions
        values = [SHARED_LABEL] + versions
        self._select.set_values(values)
        cur = self._select.get()
        if cur and cur not in values:
            self._select.set(SHARED_LABEL)

    # ------------------------------------------------------------ 对外接口

    def set_version(self, version_id: str, game_dir=None) -> None:
        """切换要管理的实例（版本），并重新加载列表。

        ``game_dir`` 给了就临时改用这个游戏目录；不给则回到 ``app.cfg.game_dir``。
        指定版本不在已安装列表里时退回「共用目录」，避免指向不存在的路径。
        """
        self._game_dir = Path(game_dir) if game_dir is not None else None
        self._sync_versions()
        values = [SHARED_LABEL] + self._versions
        vid = version_id or SHARED_LABEL
        self._select.set(vid if vid in values else SHARED_LABEL)
        self.reload()

    def refresh(self) -> None:
        """重扫版本列表和当前目录（外面改过文件之后调用）。"""
        self._sync_versions()
        self.reload()

    def handle_drop(self, paths) -> bool:
        """拖动进来的文件直接装进当前类型目录，已处理过返回 True。"""
        all_paths = [Path(p) for p in paths]
        files = [p for p in all_paths if p.suffix.lower() in (".jar", ".zip")]
        if not files:
            if all_paths:
                self.app.notify("只支持拖入 .jar / .zip 文件", "warn")
            return False
        self._import_paths(files)
        return True

    # ------------------------------------------------------------ 数据

    def _on_type_change(self, label: str) -> None:
        for key, text in CONTENT_TYPES:
            if text == label:
                self._type = key
                break
        self.reload()

    def reload(self) -> None:
        """重新读取当前目录并重建列表。

        内容没变就直接返回：切页签、切实例、主题重建都会走到这里，
        100 多行 × 8 个控件重建一次要 0.6 秒，用户感受就是"切换很卡"。
        用 (目录, 文件名/大小/启用状态) 做签名，只有真的变了才重建。
        """
        base = self._base()
        d = self._dir_for(base)
        if self._type == "mods":
            entries = list_mods(base)
        else:
            entries = _list_files(d)
        sig = (str(d), tuple((e.name, e.size, e.enabled) for e in entries))
        if sig == self._sig and self._type == self._sig_type:
            return
        self._sig = sig
        self._sig_type = self._type

        for w in self._scroll.inner.winfo_children():
            w.destroy()
        self._rows.clear()
        self._selected = None
        self._toggle_btn.set_enabled(False)
        self._delete_btn.set_enabled(False)

        self._entries = entries

        self._path_label.configure(text=str(d))
        if base != self._game():
            self._inst_hint.configure(text="已隔离：只影响这个版本", fg=ACCENT)
        else:
            self._inst_hint.configure(text="所有版本共用", fg=FG_FAINT)

        hint = TYPE_HINTS.get(self._type, "")
        self._type_hint.configure(
            text=hint, fg=DANGER if self._type == "datapacks" else WARN)
        if hint:
            if not self._type_hint.winfo_manager():
                self._type_hint.pack(fill="x", pady=(0, 8), before=self._card)
        else:
            self._type_hint.pack_forget()

        enabled = sum(1 for m in self._entries if m.enabled)
        self._count_label.configure(text=f"{len(self._entries)} 个 · 启用 {enabled}")

        if not self._entries:
            self._add_empty(d)
            return

        for entry in self._entries:
            self._add_row(entry)

    def _add_empty(self, d: Path) -> None:
        """空目录提示：说明这里是空的，并给出确切的路径。"""
        box = tk.Frame(self._scroll.inner, bg=BG_ALT)
        box.pack(fill="x", pady=30)
        inner = tk.Frame(box, bg=BG_ALT)
        inner.pack()
        tk.Label(inner, text=f"{d.name or '目录'} 是空的", bg=BG_ALT, fg=FG_DIM,
                 font=self.app.fonts["body"]).pack()
        tk.Label(inner, text=str(d), bg=BG_ALT, fg=FG_FAINT,
                 font=self.app.fonts["small"]).pack(pady=(4, 0))
        tip = tk.Frame(inner, bg=BG_HOVER)
        tip.pack(pady=(12, 0))
        tk.Label(tip, text="把 .jar / .zip 文件拖进窗口即可导入", bg=BG_HOVER,
                 fg=FG_DIM, font=self.app.fonts["small"]).pack(padx=12, pady=6)

    def _add_row(self, entry: ModEntry) -> None:
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

    def _pick_row(self, entry: ModEntry) -> None:
        self._selected = entry
        for key, row in self._rows.items():
            row.set_selected(key == entry.name)
        self._toggle_btn.set_enabled(True)
        self._delete_btn.set_enabled(True)
        self._toggle_btn.set_text("禁用" if entry.enabled else "启用")

    # ------------------------------------------------------------ 操作

    def open_download(self) -> None:
        """「下载」按钮：交给父级切到下载标签页。"""
        if self._on_download is not None:
            try:
                self._on_download(self._type)
            except Exception:                        # noqa: BLE001
                pass

    def toggle_selected(self) -> None:
        """启用 / 禁用当前选中的条目。"""
        if not self._selected:
            return
        entry = self._selected
        if self._type == "mods":
            ok, msg = toggle_mod(entry)
        else:
            ok, msg = _toggle_file(entry)
        if ok:
            self.app.notify(msg, "ok")
            self._log(f"{entry.name}：{msg}")
            self.reload()
        else:
            self.app.notify(msg, "err")

    def delete_selected(self) -> None:
        """删除当前选中的条目（先问一句）。"""
        if not self._selected:
            return
        entry = self._selected
        label = TYPE_LABELS.get(self._type, "文件")
        name = entry.name
        if not messagebox.askyesno("确认删除", f"确定要删除这个{label}吗？\n\n{name}",
                                   parent=self):
            return
        if self._type == "mods":
            ok, msg = delete_mod(entry)
        else:
            ok, msg = _delete_file(entry)
        if ok:
            self.app.notify(f"已删除 {name}", "ok")
            self._log(f"删除 {name}")
            self.reload()
        else:
            messagebox.showerror("删除失败", msg, parent=self)

    def import_dialog(self) -> None:
        """选本地文件导入到当前内容目录。"""
        label = TYPE_LABELS.get(self._type, "文件")
        files = filedialog.askopenfilenames(
            parent=self, title=f"选择要导入的{label}",
            filetypes=[("Mod / 压缩包", "*.jar *.zip"), ("所有文件", "*.*")])
        if not files:
            return
        self._import_paths([Path(f) for f in files])

    def _import_paths(self, files: list[Path]) -> None:
        """把文件装进当前类型目录，并汇报结果。"""
        base = self._base()
        d = self._dir_for(base)
        label = TYPE_LABELS.get(self._type, "文件")
        if self._type == "mods":
            ok, errors = import_mods(base, files)
        else:
            ok, errors = _import_files(d, files)
        if ok:
            self.app.notify(f"已导入 {ok} 个{label}", "ok")
            self._log(f"导入 {ok} 个文件到 {d}")
        if errors:
            self._log(f"有 {len(errors)} 个文件没导入：{errors[0]}")
            messagebox.showwarning("部分未导入", "\n".join(errors[:10]), parent=self)
        self.reload()

    def open_dir(self) -> None:
        """在系统文件管理器里打开当前内容目录。"""
        open_folder(self._dir())

    # ------------------------------------------------------------ 内部

    def _log(self, message: str) -> None:
        """写父级日志（回调可能来自别的线程，所以自己吞掉异常）。"""
        if self._on_log is None:
            return
        try:
            self._on_log(message)
        except Exception:                            # noqa: BLE001
            pass
