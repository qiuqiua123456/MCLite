"""mods 目录管理：列出、启用/禁用、删除、导入。"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

DISABLED_SUFFIX = ".disabled"


@dataclass
class ModEntry:
    name: str                # 显示名（去掉 .disabled）
    path: Path
    size: int
    enabled: bool

    @property
    def size_text(self) -> str:
        n = float(self.size)
        for unit in ("B", "KB", "MB"):
            if n < 1024 or unit == "MB":
                return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
            n /= 1024
        return f"{n:.1f} MB"


def mods_dir(game_dir: Path) -> Path:
    return Path(game_dir) / "mods"


def list_mods(game_dir: Path) -> list[ModEntry]:
    d = mods_dir(game_dir)
    if not d.is_dir():
        return []
    out: list[ModEntry] = []
    try:
        for p in d.iterdir():
            if not p.is_file():
                continue
            low = p.name.lower()
            if low.endswith(".jar"):
                enabled = True
                display = p.name
            elif low.endswith(".jar" + DISABLED_SUFFIX):
                enabled = False
                display = p.name[: -len(DISABLED_SUFFIX)]
            else:
                continue
            out.append(ModEntry(name=display, path=p, size=p.stat().st_size, enabled=enabled))
    except OSError:
        return []
    out.sort(key=lambda m: m.name.lower())
    return out


def toggle_mod(entry: ModEntry) -> tuple[bool, str]:
    """切换启用状态，返回 (成功, 新状态/错误)。"""
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
        return True, "已禁用" if entry.enabled else "已启用"
    except OSError as exc:
        return False, f"重命名失败：{exc}"


def delete_mod(entry: ModEntry) -> tuple[bool, str]:
    try:
        entry.path.unlink()
        return True, "已删除"
    except OSError as exc:
        return False, f"删除失败：{exc}"


def import_mods(game_dir: Path, files: list[Path]) -> tuple[int, list[str]]:
    d = mods_dir(game_dir)
    d.mkdir(parents=True, exist_ok=True)
    ok = 0
    errors: list[str] = []
    for f in files:
        try:
            target = d / f.name
            if target.exists():
                errors.append(f"已存在，跳过：{f.name}")
                continue
            shutil.copy2(f, target)
            ok += 1
        except OSError as exc:
            errors.append(f"{f.name}: {exc}")
    return ok, errors


def open_folder(path: Path) -> None:
    import os
    import subprocess
    import sys
    path.mkdir(parents=True, exist_ok=True)
    try:
        if sys.platform == "win32":
            os.startfile(str(path))                     # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError:
        pass
