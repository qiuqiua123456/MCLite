"""探针：把顶层窗口类的背景画刷刷成纯色，看无边框窗口顶上那条 7px 会不会变色。

如果变色 ⇒ 那 7px 是非客户区被「窗口类背景画刷」填的，改画刷就能让它跟顶栏
同色，不必 subclass WndProc 去抢 WM_NCCALCSIZE。
"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

sys.path.insert(0, ".")

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.GetParent.argtypes = [wintypes.HWND]
user32.GetParent.restype = wintypes.HWND
if ctypes.sizeof(ctypes.c_void_p) == 8:
    user32.SetClassLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    user32.SetClassLongPtrW.restype = ctypes.c_ssize_t
else:
    user32.SetClassLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    user32.SetClassLongW.restype = ctypes.c_long
gdi32.CreateSolidBrush.argtypes = [wintypes.DWORD]
gdi32.CreateSolidBrush.restype = wintypes.HGDIOBJ

GCLP_HBRBACKGROUND = -10


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
    end = time.time() + 1.2
    while time.time() < end:
        app.update()
        time.sleep(0.02)

    hwnd = frameless.hwnd_of(app)
    print(f"hwnd=0x{hwnd:X}")

    # COLORREF 是 0x00BBGGRR —— 纯红
    brush = gdi32.CreateSolidBrush(0x000000FF)
    print(f"brush={brush}")
    setter = user32.SetClassLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user32.SetClassLongW
    old = setter(wintypes.HWND(hwnd), GCLP_HBRBACKGROUND, brush)
    print(f"old brushed = 0x{int(old) & 0xFFFFFFFFFFFFFFFF:X}")

    # 强制重算非客户区，否则那条已经画好的边框不会变色
    user32.SetWindowPos(wintypes.HWND(hwnd), None, 0, 0, 0, 0,
                        0x0001 | 0x0002 | 0x0004 | 0x0020 | 0x0040)  # NOSIZE|NOMOVE|NOZORDER|FRAMECHANGED|SHOWWINDOW
    user32.RedrawWindow(wintypes.HWND(hwnd), None, None, 0x0001 | 0x0080 | 0x0100)

    end = time.time() + 1.2
    while time.time() < end:
        app.update()
        time.sleep(0.02)

    r = wintypes.RECT()
    user32.GetClientRect(wintypes.HWND(hwnd), ctypes.byref(r))
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(wintypes.HWND(hwnd), ctypes.byref(pt))
    print(f"client top-left on screen = {pt.x},{pt.y}")

    # 用 screen capture 看那 7px
    import probe_fl_screen as P
    img = P.grab_screen(pt.x - 4, pt.y - 12, 400, 24)
    img.save("shots/fl_brush.png")
    print("y=0 是客户区顶端上方 12px；看红/蓝交界：")
    for y in range(0, 20):
        print(f"  y={y:2d} {img.getpixel((200, y))}")

    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
