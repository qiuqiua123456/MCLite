"""界面用的位图素材。

Tk 8.6 自带 PNG 解码，所以这里只用 ``tk.PhotoImage``，不引入 Pillow。
图片的圆角、压暗、淡出等问题在 ``tools/make_ui_assets.py`` 里离线烤好，
运行期只负责按名字取图并缓存。
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path

_CACHE: dict[str, tk.PhotoImage | None] = {}


def ui_dir() -> Path | None:
    """返回 assets/ui 目录（源码运行与 PyInstaller 单文件都能找到）。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        cand = Path(base) / "assets" / "ui"
        if cand.is_dir():
            return cand
    here = Path(__file__).resolve().parent.parent.parent / "assets" / "ui"
    if here.is_dir():
        return here
    exe = Path(sys.executable).resolve().parent / "assets" / "ui"
    if exe.is_dir():
        return exe
    return None


def load(master: tk.Misc, name: str) -> tk.PhotoImage | None:
    """按文件名取图（不含后缀），找不到就返回 None。"""
    if name in _CACHE:
        return _CACHE[name]
    photo: tk.PhotoImage | None = None
    root = ui_dir()
    if root is not None:
        path = root / f"{name}.png"
        if path.is_file():
            try:
                photo = tk.PhotoImage(master=master, file=str(path))
            except tk.TclError:
                photo = None
    _CACHE[name] = photo
    return photo
