"""探针：无边框窗口顶部那条 7px 灰带到底由谁绘制。

逐个尝试 DWM 属性和 Win32 手段，每改一个就抓真实屏幕像素看那条带变没变色：
  A. DWMWA_BORDER_COLOR (34) = 红
  B. DWMWA_CAPTION_COLOR (35) = 红
  C. teardown 让 Tk 背景 = 红
  D. 类背景画刷 = 红（前面已单独测过，不变色，这里复核）
哪一项让带子变红，就用它把带子染成顶栏色。
"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

sys.path.insert(0, ".")

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
dwmapi = ctypes.windll.dwmapi

user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
dwmapi.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD,
                                         ctypes.c_void_p, wintypes.DWORD]
dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long

DWMWA_BORDER_COLOR = 34
DWMWA_CAPTION_COLOR = 35

RED = 0x000000FF          # COLORREF 0x00BBGGRR


def set_attr(hwnd, attr, value):
    v = wintypes.DWORD(value)
    hr = dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd), attr,
                                      ctypes.byref(v), ctypes.sizeof(v))
    return hr


def band_colors(app, frameless):
    """返回 (客户区上方第 3px, 第 5px) 两个采样点颜色。"""
    import probe_fl_screen as P
    hwnd = frameless.hwnd_of(app)
    r = wintypes.RECT()
    user32.GetClientRect(wintypes.HWND(hwnd), ctypes.byref(r))
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(wintypes.HWND(hwnd), ctypes.byref(pt))
    img = P.grab_screen(pt.x - 4, pt.y - 12, 400, 24)
    # 客户区顶端在 y=12；带子在 y=6..11
    return img.getpixel((200, 7)), img.getpixel((200, 10))


def main() -> int:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:                              # noqa: BLE001
        pass

    from mclite.ui import frameless
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

    print("基线:", band_colors(app, frameless))

    print("A. DWMWA_BORDER_COLOR = 红 ->", set_attr(hwnd, DWMWA_BORDER_COLOR, RED))
    settle()
    print("   带子:", band_colors(app, frameless))

    print("B. DWMWA_CAPTION_COLOR = 红 ->", set_attr(hwnd, DWMWA_CAPTION_COLOR, RED))
    settle()
    print("   带子:", band_colors(app, frameless))

    print("C. Tk 顶层 bg = 红")
    try:
        app.configure(bg="#FF0000")
    except Exception as exc:                       # noqa: BLE001
        print("   失败:", exc)
    settle()
    print("   带子:", band_colors(app, frameless))

    print("D. 类背景画刷 = 红")
    brush = gdi32.CreateSolidBrush(RED)
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        user32.SetClassLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        user32.SetClassLongPtrW.restype = ctypes.c_ssize_t
        user32.SetClassLongPtrW(wintypes.HWND(hwnd), -10, brush)
    settle()
    print("   带子:", band_colors(app, frameless))

    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
