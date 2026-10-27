"""给微软登录弹窗截图。"""

from __future__ import annotations

import ctypes
import sys
import time
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mclite.ui.app import App  # noqa: E402
from mclite.ui.ms_login import MsLoginDialog  # noqa: E402

from test_exe import capture_window  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "shots"
OUT.mkdir(exist_ok=True)

_GW_OWNER = 4


def grab(win, name: str) -> None:
    """用 PrintWindow 抓窗口本身，避免被别的窗口盖住。"""
    win.update_idletasks()
    win.update()
    time.sleep(0.3)
    root = ctypes.windll.user32.GetAncestor(win.winfo_id(), _GW_OWNER) or win.winfo_id()
    img = capture_window(root)
    path = OUT / name
    img.save(path)
    print("saved ->", path, img.size)


def pump(app, seconds: float) -> None:
    """边跑事件循环边等，after() 排的回调才会真正执行。"""
    end = time.time() + seconds
    while time.time() < end:
        try:
            app.update()
        except tk.TclError:
            return
        time.sleep(0.05)


def main() -> int:
    app = App()
    app.show_page("home")
    pump(app, 2.5)
    grab(app, "login_home_btn.png")

    dlg = MsLoginDialog(app)
    pump(app, 5.0)           # 等设备码回来（走网络 + 主线程队列）
    grab(dlg, "login_dialog.png")

    dlg._cancel.set()
    dlg.destroy()
    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
