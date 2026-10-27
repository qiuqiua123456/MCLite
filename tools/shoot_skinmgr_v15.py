"""截图皮肤管理弹窗（1.5.0：新增 NameMC 查看、衣柜探测）。"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("MCLITE_NO_BROWSER", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mclite.ui.app import App                 # noqa: E402
from mclite.ui.skin_mgr_dialog import SkinDialog  # noqa: E402
from tools.test_exe import capture_window     # noqa: E402

SHOTS = Path(__file__).resolve().parent.parent / "shots"


def pump(app, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.03)


def main() -> None:
    app = App()
    app.create_pages()
    pump(app, 0.8)

    dlg = SkinDialog(app)
    dlg.grab_set()
    pump(app, 2.5)

    out = SHOTS / "skin_mgr_v15.png"
    SHOTS.mkdir(exist_ok=True)
    capture_window(dlg.winfo_id()).save(out)
    print("saved:", out)
    print("account:", getattr(dlg._account(), "name", None))

    dlg.destroy()
    app.destroy()


if __name__ == "__main__":
    main()
