"""在几个较小的窗口尺寸下真实截图，检查控件有没有被裁掉。

跑法：G:\\python\\python.exe tools\\shot_small.py [page] [w] [h]
不带参数时按 home/install/settings × 几档尺寸全部拍一遍。
"""
from __future__ import annotations

import ctypes
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from probe_fl_screen import grab_screen  # noqa: E402

SIZES = ((1160, 724), (1000, 640), (900, 580), (880, 560), (820, 520), (760, 470))
PAGES = ("home", "install", "settings")
OUT = Path("shots")


def pump(app, sec: float) -> None:
    end = time.perf_counter() + sec
    while time.perf_counter() < end:
        try:
            app.update()
        except Exception:                            # noqa: BLE001
            return
        time.sleep(0.02)


def shoot(app, name: str) -> None:
    from mclite.ui import frameless
    from ctypes import wintypes

    app.deiconify()
    app.lift()
    app.attributes("-topmost", True)
    app.update()
    app.focus_force()
    pump(app, 0.45)
    u = ctypes.windll.user32
    u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    r = wintypes.RECT()
    hwnd = frameless.hwnd_of(app)
    u.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(r))
    img = grab_screen(r.left, r.top, r.right - r.left, r.bottom - r.top)
    p = OUT / f"small_{name}.png"
    img.save(p)
    print(f"  saved {p}  ({r.right - r.left}x{r.bottom - r.top})", flush=True)
    app.attributes("-topmost", False)


def main() -> int:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:                                # noqa: BLE001
        pass

    from mclite.ui.app import App

    only_page = sys.argv[1] if len(sys.argv) > 1 else ""
    pages = (only_page,) if only_page else PAGES

    app = App()
    app.create_pages()
    app.show_page("home")
    pump(app, 1.2)
    print(f"minsize = {app.minsize()}", flush=True)

    for page in pages:
        app.show_page(page)
        pump(app, 0.8)
        for w, h in SIZES:
            app.geometry(f"{w}x{h}+60+60")
            pump(app, 0.9)
            real_w, real_h = app.winfo_width(), app.winfo_height()
            shoot(app, f"{page}_{w}x{h}")
            print(f"  请求 {w}x{h} → 实际 {real_w}x{real_h}", flush=True)

    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
