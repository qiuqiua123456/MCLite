"""截图崩溃诊断弹窗（用真实日志 + 一条人为加入的 OOM 结论）。"""

from __future__ import annotations

import ctypes
import sys
import time
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from mclite import crash  # noqa: E402
from mclite.ui.app import App  # noqa: E402
from mclite.ui.crash_dialog import CrashDialog  # noqa: E402

from test_exe import capture_window  # noqa: E402

_GW_OWNER = 4


def grab(win, name: str) -> None:
    win.update_idletasks()
    win.update()
    time.sleep(0.3)
    root = ctypes.windll.user32.GetAncestor(win.winfo_id(), _GW_OWNER) or win.winfo_id()
    img = capture_window(root)
    path = ROOT / "shots" / name
    img.save(path)
    print("saved ->", path, img.size)


def pump(app, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        try:
            app.update()
        except tk.TclError:
            return
        time.sleep(0.03)


def main() -> int:
    app = App()
    app.update()
    app.cfg.set("game_dir", r"G:\.minecraft")
    sample = """
[01:02:03] [main/ERROR]: java.lang.OutOfMemoryError: Java heap space
        at net.minecraft.client.Minecraft.<init>(Minecraft.java:500)
[01:02:03] [main/ERROR]: java.lang.NoSuchMethodError: net.minecraft.Util.m_1()
[01:02:03] [main/ERROR]: Missing or unsupported mandatory dependencies
    Mod ID: 'sodium', Requested by: 'iris'
[01:02:03] [main/ERROR]: GLFW error 65542: WGL: The driver does not appear to support OpenGL
Description: Rendering overlay
"""
    diags = crash.analyze(sample)
    dlg = CrashDialog(app, "1.20.1", diags, None)
    pump(app, 0.6)
    grab(dlg, "crash_dialog.png")
    print("诊断条数:", len(diags), [d.title for d in diags])
    dlg.destroy()
    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
