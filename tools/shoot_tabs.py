"""截图：开始页三个页签（启动 / 模组 / 账户）。"""

from __future__ import annotations

import ctypes
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:                                  # noqa: BLE001
        pass

SHOTS = ROOT / "shots"


def pump(app, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.update_idletasks()
        app.update()
        time.sleep(0.02)


def grab(app, name: str) -> None:
    SHOTS.mkdir(exist_ok=True)
    path = SHOTS / f"{name}.png"
    try:
        from test_exe import capture_window          # noqa: PLC0415
        img = capture_window(app.winfo_id())
    except Exception:                                  # noqa: BLE001
        from PIL import ImageGrab                      # noqa: PLC0415
        x, y = app.winfo_rootx(), app.winfo_rooty()
        w, h = app.winfo_width(), app.winfo_height()
        img = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
    img.save(path)
    print(f"saved -> {path}")


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from mclite.ui.app import App

    app = App()
    app.create_pages()
    pump(app, 0.4)
    app.show_page("home")
    pump(app, 2.0)          # 留时间让预建面板跑完

    home = app._pages["home"]
    for key in ("launch", "mods", "account"):
        home.show_tab(key)
        pump(app, 1.0)
        grab(app, f"tabs_{key}")

    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
