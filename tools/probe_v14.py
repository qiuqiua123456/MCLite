"""1.4 收尾自检：主题热切换 + 头像绘制 + 中文搜索 + 账号区按钮。

用法：python tools/probe_v14.py [theme|avatar|all]
"""

from __future__ import annotations

import ctypes
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:                                   # noqa: BLE001
        pass

SHOTS = ROOT / "shots"


def pump(app, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.update_idletasks()
        app.update()
        time.sleep(0.03)


def grab(win, out: Path) -> None:
    from test_exe import capture_window
    win.update_idletasks()
    win.update()
    win.lift()
    win.update()
    img = capture_window(win.winfo_id())
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print("  saved ->", out.name, img.size)


def make_app():
    from mclite.ui.app import App
    app = App()
    app.create_pages()
    pump(app, 1.2)
    return app


def probe_theme() -> None:
    from mclite.ui import theme
    app = make_app()
    app.show_page("home")
    pump(app, 0.8)
    print("当前主题:", theme.THEME, "BG =", theme.BG)
    for key in theme.THEME_ORDER:
        if key == theme.THEME:
            continue
        app.apply_theme(key)
        pump(app, 1.6)
        print(f"切到 {key}: THEME={theme.THEME} BG={theme.BG} 页面={sorted(app._pages)}")
        grab(app, SHOTS / f"theme_{key}.png")
    app.apply_theme("dark")
    pump(app, 1.4)
    print("还原 dark: BG =", theme.BG)
    app.destroy()


def probe_avatar() -> None:
    from mclite import skins
    from mclite.ui.widgets import Avatar
    import tkinter as tk
    app = make_app()
    acc = app.current_account()
    print("账号:", getattr(acc, "name", None), getattr(acc, "uuid", None), "kind", getattr(acc, "kind", None))
    png = None
    if acc is not None:
        api = acc.api if getattr(acc, "third_party", False) else ""
        t = time.time()
        prof = skins.profile(acc.uuid, api)
        print("profile:", prof.get("name"), "skin:", bool(prof.get("skin")), "cape:", bool(prof.get("cape")), f"{time.time()-t:.2f}s")
        png = skins.fetch_skin_png(acc.uuid, api)
        print("skin png:", len(png) if png else None, "bytes")
    win = tk.Toplevel(app)
    win.title("头像测试")
    win.configure(bg="white")
    for size in (32, 64, 128):
        av = Avatar(win, size=size, bg="white")
        av.pack(padx=12, pady=8, side="left")
        if png:
            av.draw_skin(png)
        else:
            av.draw_letter("Q")
    pump(app, 0.6)
    grab(win, SHOTS / "avatar_probe.png")
    win.destroy()
    app.destroy()


def main() -> int:
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which in ("theme", "all"):
        probe_theme()
    if which in ("avatar", "all"):
        probe_avatar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
