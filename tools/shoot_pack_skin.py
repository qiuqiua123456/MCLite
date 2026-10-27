"""截皮肤站登录弹窗和整合包市场弹窗。"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("MCLITE_NO_BROWSER", "1")   # 截图时别真开浏览器

import ctypes
import time
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from mclite.ui.app import App  # noqa: E402

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

    from mclite.ui.pack_dialog import PackMarketDialog
    from mclite.ui.skin_dialog import SkinLoginDialog

    dlg = SkinLoginDialog(app)
    dlg._user_var.set("player@example.com")
    dlg._pass_var.set("password")
    pump(app, 0.8)
    grab(dlg, "skin_login.png")
    dlg.destroy()

    market = PackMarketDialog(app)
    market._query.delete(0, "end")
    market._query.insert(0, "fabulously")
    market._search()
    pump(app, 8.0)
    grab(market, "pack_market.png")
    print("结果数:", len(market._projects))
    market.destroy()

    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
