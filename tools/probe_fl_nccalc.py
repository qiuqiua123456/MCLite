"""探针：用 WM_NCCALCSIZE 把非客户区彻底吃掉，看顶部那条 7px 灰带是否消失。

做法：subclass 顶层窗口的 WndProc，只截 WM_NCCALCSIZE（wParam=TRUE 时返回 0，
表示客户区 = 整个窗口矩形），其它消息一律 CallWindowProcW 转发给 Tk 原来的
回调。最大化时必须把客户区收进工作区，否则内容会溢出屏幕 7px。

验证：真实屏幕抓像素，看窗口顶端到蓝色顶栏之间还有没有 243 灰带。
"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

sys.path.insert(0, ".")

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]

WM_NCCALCSIZE = 0x0083

if ctypes.sizeof(ctypes.c_void_p) == 8:
    SetWndProc = user32.SetWindowLongPtrW
    SetWndProc.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    SetWndProc.restype = ctypes.c_ssize_t
    GetWndProc = user32.GetWindowLongPtrW
    GetWndProc.argtypes = [wintypes.HWND, ctypes.c_int]
    GetWndProc.restype = ctypes.c_ssize_t
else:
    SetWndProc = user32.SetWindowLongW
    SetWndProc.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    SetWndProc.restype = ctypes.c_long
    GetWndProc = user32.GetWindowLongW
    GetWndProc.argtypes = [wintypes.HWND, ctypes.c_int]

user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT,
                                   wintypes.WPARAM, wintypes.LPARAM]
user32.CallWindowProcW.restype = ctypes.c_ssize_t
user32.IsZoomed.argtypes = [wintypes.HWND]
user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.MonitorFromWindow.restype = wintypes.HMONITOR
user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.c_void_p]

GWLP_WNDPROC = -4
MONITOR_DEFAULTTONEAREST = 2
WNDPROCTYPE = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                                 wintypes.WPARAM, wintypes.LPARAM)


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


class NCCALCSIZE_PARAMS(ctypes.Structure):
    _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]


class Frame:
    """保存 subclass 状态，必须一直持有 _proc，否则回调被 GC 掉会崩。"""

    def __init__(self, hwnd):
        self.hwnd = hwnd
        self.old = int(GetWndProc(wintypes.HWND(hwnd), GWLP_WNDPROC))
        self._proc = WNDPROCTYPE(self._wndproc)
        SetWndProc(wintypes.HWND(hwnd), GWLP_WNDPROC,
                   ctypes.cast(self._proc, ctypes.c_void_p).value)
        self.calls = {"nccalc": 0, "zoom": 0}

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_NCCALCSIZE and wparam:
            self.calls["nccalc"] += 1
            if user32.IsZoomed(wintypes.HWND(hwnd)):
                self.calls["zoom"] += 1
                params = ctypes.cast(lparam, ctypes.POINTER(NCCALCSIZE_PARAMS))
                mi = MONITORINFO()
                mi.cbSize = ctypes.sizeof(MONITORINFO)
                mon = user32.MonitorFromWindow(wintypes.HWND(hwnd), MONITOR_DEFAULTTONEAREST)
                user32.GetMonitorInfoW(mon, ctypes.byref(mi))
                params.contents.rgrc[0] = mi.rcWork
            return 0
        return user32.CallWindowProcW(ctypes.c_void_p(self.old), wintypes.HWND(hwnd),
                                      msg, wparam, lparam)

    def restore(self):
        if self.old:
            SetWndProc(wintypes.HWND(self.hwnd), GWLP_WNDPROC, self.old)
            self.old = 0


def sample(app, frameless, label):
    import probe_fl_screen as P
    hwnd = frameless.hwnd_of(app)
    r = wintypes.RECT()
    user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(r))
    c = wintypes.RECT()
    user32.GetClientRect(wintypes.HWND(hwnd), ctypes.byref(c))
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(wintypes.HWND(hwnd), ctypes.byref(pt))
    print(f"{label}: 窗口={r.left},{r.top},{r.right},{r.bottom}  客户区屏幕原点={pt.x},{pt.y}")
    img = P.grab_screen(r.left, r.top, 500, 60)
    img.save(f"shots/fl_{label.replace(' ', '_')}.png")
    print("   窗口顶端往下逐行颜色（x=250）:")
    run = []
    for y in range(0, 30):
        col = img.getpixel((250, y))
        if not run or run[-1][0] != col:
            run.append([col, y, y])
        else:
            run[-1][2] = y
    for col, a, b in run:
        print(f"     y={a:2d}..{b:2d}  {col}")


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

    def settle(sec=0.9):
        end = time.time() + sec
        while time.time() < end:
            app.update()
            time.sleep(0.02)

    settle(1.2)
    sample(app, frameless, "before")

    hwnd = frameless.hwnd_of(app)
    f = Frame(hwnd)
    user32.SetWindowPos(wintypes.HWND(hwnd), None, 0, 0, 0, 0,
                        0x0001 | 0x0002 | 0x0004 | 0x0020 | 0x0040)
    user32.RedrawWindow(wintypes.HWND(hwnd), None, None, 0x0001 | 0x0080 | 0x0100)
    settle(1.2)
    sample(app, frameless, "after")
    print("nccalc 调用次数:", f.calls)

    # 最大化再抓一次，确认内容不会溢出屏幕
    frameless.toggle_maximize(app)
    settle(1.2)
    sample(app, frameless, "max")
    hwnd = frameless.hwnd_of(app)
    r = wintypes.RECT()
    user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(r))
    print(f"最大化窗口矩形={r.left},{r.top},{r.right},{r.bottom}")
    frameless.toggle_maximize(app)
    settle(0.8)

    f.restore()
    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
