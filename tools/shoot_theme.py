"""切换主题后逐页截图，核对亮色主题是否真的整屏变亮。

用法：
    python tools/shoot_theme.py light [prefix]
"""

from __future__ import annotations

import ctypes
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:                                  # noqa: BLE001
        pass

OUT = Path(__file__).resolve().parent.parent / "shots"

PAGES = ("home", "install", "settings")


def pump(app, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.update_idletasks()
        app.update()
        time.sleep(0.02)


def grab(app, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.png"
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from test_exe import capture_window            # noqa: PLC0415
        img = capture_window(app.winfo_id())
    except Exception:                                  # noqa: BLE001
        from PIL import ImageGrab                      # noqa: PLC0415
        x, y = app.winfo_rootx(), app.winfo_rooty()
        w, h = app.winfo_width(), app.winfo_height()
        img = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
    img.save(path)
    print(f"saved -> {path}")


def main() -> int:
    theme = sys.argv[1] if len(sys.argv) > 1 else "light"
    prefix = sys.argv[2] if len(sys.argv) > 2 else f"theme_{theme}"
    from mclite.ui.app import App

    app = App()
    app.create_pages()
    pump(app, 0.5)

    # 记下原来的主题，跑完恢复，别把用户存的选择改掉
    original = str(app.cfg.get("theme") or "pcl")

    # 真的走一遍用户路径：设置页点主题按钮 → apply_theme → 重建界面
    app.apply_theme(theme)
    pump(app, 1.2)

    for page_name in PAGES:
        app.show_page(page_name)
        pump(app, 0.8)
        grab(app, f"{prefix}_{page_name}")

    if original != theme:
        app.apply_theme(original)
        pump(app, 1.0)
    print(f"theme restored -> {original}")

    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
