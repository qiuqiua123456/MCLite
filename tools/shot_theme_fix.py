"""截图验收「切主题后设置页」：确认整页都在窗口内，右侧按钮没被推到外面。"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_fl_screen import grab_screen  # noqa: E402


def settle(app, sec=1.2):
    end = time.time() + sec
    while time.time() < end:
        try:
            app.update()
        except Exception:                          # noqa: BLE001
            return
        time.sleep(0.02)


def shoot(app, name):
    # 必须先把窗口提到最前：这个脚本跑在终端/浏览器后面，直接抓屏幕会把
    # 别人的窗口拍进来（之前就拍到了背后的浏览器）。
    try:
        app.deiconify()
        app.lift()
        app.attributes("-topmost", True)
        app.update()
        app.focus_force()
    except Exception:                              # noqa: BLE001
        pass
    settle(app, 0.5)
    app.update_idletasks()
    app.update()
    x, y = app.winfo_rootx(), app.winfo_rooty()
    w, h = app.winfo_width(), app.winfo_height()
    img = grab_screen(x, y, w, h)
    try:
        app.attributes("-topmost", False)
    except Exception:                              # noqa: BLE001
        pass
    out = Path(__file__).resolve().parent.parent / "shots" / name
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print("  截图:", out, img.size)


def main() -> int:
    from mclite.ui.app import App

    app = App()
    app.create_pages()
    app.show_page("settings")
    settle(app, 1.5)
    shoot(app, "fix_settings_before.png")

    app._pages["settings"]._set_theme("dark")
    settle(app, 2.0)
    shoot(app, "fix_settings_after_dark.png")

    app._pages["settings"]._set_theme("pcl")
    settle(app, 2.0)
    shoot(app, "fix_settings_after_pcl.png")

    # 顺带存一张首页，确认其它页没被弄坏
    app.show_page("home")
    settle(app, 1.0)
    shoot(app, "fix_home_after.png")

    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
