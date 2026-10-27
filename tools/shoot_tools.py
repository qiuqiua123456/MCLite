"""给新增的三个弹窗截图：存档管理 / 完整性检查 / 皮肤管理。"""

from __future__ import annotations

import ctypes
import sys
import time
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mclite.ui.app import App  # noqa: E402
from mclite.ui.skin_mgr_dialog import SkinDialog  # noqa: E402
from mclite.ui.verify_dialog import VerifyDialog  # noqa: E402
from mclite.ui.world_dialog import WorldDialog  # noqa: E402

from test_exe import capture_window  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "shots"
OUT.mkdir(exist_ok=True)
_GW_OWNER = 4


def grab(win, name: str) -> None:
    win.update_idletasks()
    win.update()
    time.sleep(0.3)
    root = ctypes.windll.user32.GetAncestor(win.winfo_id(), _GW_OWNER) or win.winfo_id()
    img = capture_window(root)
    path = OUT / name
    img.save(path)
    print("saved ->", path, img.size)


def pump(app, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        try:
            app.update()
        except tk.TclError:
            return
        time.sleep(0.05)


def main() -> int:
    app = App()
    app.create_pages()
    app.show_page("home")
    pump(app, 3.0)

    home = app._pages["home"]
    print("选中版本:", home._selected)
    game_dir = Path(app.cfg.game_dir)
    inst = home._instance_dir()

    dlg = WorldDialog(app, inst / "saves", str(home._selected or ""))
    dlg.grab_set()
    pump(app, 1.2)
    grab(dlg, "world_dialog.png")
    dlg._close()

    dlg2 = VerifyDialog(app, str(home._selected or ""))
    dlg2.grab_set()
    pump(app, 6.0)
    grab(dlg2, "verify_dialog.png")
    dlg2._close()

    dlg3 = SkinDialog(app)
    dlg3.grab_set()
    pump(app, 3.0)
    grab(dlg3, "skin_mgr.png")
    dlg3._close()

    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
