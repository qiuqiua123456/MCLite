"""验收：换主题后窗口顶端那条 7px 边也要跟着换成新主题的顶栏色。

换主题走 `App.apply_theme` → `after(30, _rebuild)` → `_build()` → `_apply_frameless()`，
所以 caption 色应该自动跟上。这里逐主题抓真实屏幕像素核对。
"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

sys.path.insert(0, ".")

user32 = ctypes.windll.user32
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]

FAIL: list[str] = []


def check(cond, msg):
    if not cond:
        FAIL.append(msg)
    print(("  ok   " if cond else "  FAIL ") + msg)


def near(px, rgb, tol=26):
    return all(abs(a - b) <= tol for a, b in zip(px, rgb))


def css(color):
    h = color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def main() -> int:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:                              # noqa: BLE001
        pass

    import probe_fl_screen as P
    from mclite.ui import frameless, theme
    from mclite.ui.app import App

    app = App()
    app.create_pages()
    app.show_page("home")

    def settle(sec=1.0):
        end = time.time() + sec
        while time.time() < end:
            app.update()
            time.sleep(0.02)

    settle(1.5)

    for name in ("pcl", "dark", "light", "midnight", "forest"):
        app.apply_theme(name)
        settle(1.3)
        hwnd = frameless.hwnd_of(app)
        c = wintypes.RECT()
        user32.GetClientRect(wintypes.HWND(hwnd), ctypes.byref(c))
        pt = wintypes.POINT(0, 0)
        user32.ClientToScreen(wintypes.HWND(hwnd), ctypes.byref(pt))
        want = css(theme.ACCENT_DARK)
        img = P.grab_screen(pt.x + 40, pt.y - 5, 1, 5)
        px = [img.getpixel((0, r)) for r in range(5)]
        check(all(near(p, want) for p in px),
              f"{name:9s} 顶边 {want} ← 实测 {px[0]} {px[-1]}")

    app.destroy()
    print()
    print(f"FAIL {len(FAIL)} 项")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
