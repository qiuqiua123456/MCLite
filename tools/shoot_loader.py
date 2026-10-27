"""给加载器安装对话框截图。"""

from __future__ import annotations

import sys
import time
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from shoot_login import grab, pump  # noqa: E402
from mclite.ui.app import App  # noqa: E402
from mclite.ui.loader_dialog import LoaderDialog  # noqa: E402


def main() -> int:
    app = App()
    app.show_page("install")
    pump(app, 1.5)

    dlg = LoaderDialog(app, "1.20.1")
    pump(app, 6.0)
    grab(dlg, "loader_dialog.png")

    if dlg._versions:
        dlg._load("forge")
        pump(app, 8.0)
        grab(dlg, "loader_dialog_forge.png")

    dlg.destroy()
    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
