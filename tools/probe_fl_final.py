"""探针（方案定稿验证）：保留原生缩放边框，只把顶栏上方那条边框染成顶栏色。

WM_NCCALCSIZE 那套虽然能把那 7px 吃掉，但要在 Python 里 subclass WndProc，
SendMessage 自窗口时会重入 Python 回调 → 直接 `PyEval_RestoreThread` 致命错误
（实测）。而 `DWMWA_CAPTION_COLOR` 只改配色、不动任何窗口行为，缩放/贴边吸附
全部免费保留，所以最终选它。

这里验证：摘掉 WS_CAPTION 后把 caption 色设成顶栏顶部色，抓真实屏幕像素，
确认上/左/右/下四条边框都跟界面同色、没有灰边。
"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

sys.path.insert(0, ".")

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi

user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
dwmapi.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD,
                                         ctypes.c_void_p, wintypes.DWORD]
dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long

DWMWA_CAPTION_COLOR = 35
DWMWA_TEXT_COLOR = 36


def colorref(hex_color: str) -> int:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (b << 16) | (g << 8) | r


def set_color(hwnd, attr, hex_color):
    v = wintypes.DWORD(colorref(hex_color))
    return dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd), attr,
                                        ctypes.byref(v), ctypes.sizeof(v))


def main() -> int:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:                              # noqa: BLE001
        pass

    from mclite.ui import frameless, theme
    from mclite.ui.app import App

    app = App()
    app.create_pages()
    app.show_page("home")

    def settle(sec=0.8):
        end = time.time() + sec
        while time.time() < end:
            app.update()
            time.sleep(0.02)

    settle(1.2)
    hwnd = frameless.hwnd_of(app)

    import probe_fl_screen as P
    r = wintypes.RECT()
    user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(r))
    l, t, rr, b = r.left, r.top, r.right, r.bottom
    print(f"窗口=({l},{t})-({rr},{b})  顶栏顶部色={theme.ACCENT_DARK}")

    def edges(tag):
        img = P.grab_screen(l - 6, t - 6, (rr - l) + 12, (b - t) + 12)
        img.save(f"shots/fl_final_{tag}.png")
        cx, cy = img.width // 2, img.height // 2
        print(f"  [{tag}]")
        print(f"    上边框各 y: " + "  ".join(
            f"y={y}:{img.getpixel((cx, y + 6))}" for y in range(0, 9)))
        print(f"    左边框 x={6} 中段: {img.getpixel((3, cy))}  {img.getpixel((6, cy))}")
        print(f"    右边框:          {img.getpixel((img.width - 4, cy))}  "
              f"{img.getpixel((img.width - 7, cy))}")
        print(f"    下边框:          {img.getpixel((cx, img.height - 3))}  "
              f"{img.getpixel((cx, img.height - 6))}")

    edges("before")
    print("设 DWMWA_CAPTION_COLOR ->", set_color(hwnd, DWMWA_CAPTION_COLOR, theme.ACCENT_DARK))
    print("设 DWMWA_TEXT_COLOR    ->", set_color(hwnd, DWMWA_TEXT_COLOR, "#FFFFFF"))
    settle(1.0)
    edges("after")

    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
