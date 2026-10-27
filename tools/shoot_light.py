"""亮色主题下的界面截图，用来核对「切换了亮色还显示暗色」是否修好。

用法：python tools/shoot_light.py [输出前缀]
"""

from __future__ import annotations

import ctypes
import json
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
    print(f"saved -> {path}  ({img.width}x{img.height})")


def main() -> int:
    prefix = sys.argv[1] if len(sys.argv) > 1 else "light"
    from mclite.ui import theme as th
    from mclite.ui.app import App

    app = App()
    app.create_pages()
    pump(app, 0.4)

    # 就地切主题（不重启），和设置页点按钮走同一条路径
    app.apply_theme("light")
    pump(app, 1.2)
    print(f"theme={th.THEME} BG={th.BG} BG_ALT={th.BG_ALT} ACCENT={th.ACCENT}")

    home = app._pages["home"]
    app.show_page("home")
    pump(app, 3.0)
    grab(app, f"{prefix}_home")

    home.show_tab("mods")
    pump(app, 1.5)
    grab(app, f"{prefix}_mods")

    home.show_tab("account")
    pump(app, 1.0)
    grab(app, f"{prefix}_account")

    app.show_page("install")
    pump(app, 1.0)
    grab(app, f"{prefix}_install")

    app.show_page("settings")
    pump(app, 1.0)
    grab(app, f"{prefix}_settings")

    # 复原成默认主题，别把用户的配置改掉
    app.apply_theme("pcl")
    pump(app, 0.8)
    print("restored theme ->", th.THEME)

    cfg_path = Path(app.cfg.path) if getattr(app.cfg, "path", None) else None
    if cfg_path and cfg_path.is_file():
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        print(f"cfg theme = {data.get('theme')!r}")

    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
