"""探针：WM_NCCALCSIZE 吃掉非客户区后，八向缩放热区还在不在。

做法：subclass 只截 WM_NCCALCSIZE（返回 0 = 客户区等于整窗，最大化时收进工作区），
然后往窗口四边/四角/中间发 WM_NCHITTEST，看系统/ Tk 返回的命中码：
  HTCLIENT=1  HTLEFT=10  HTRIGHT=11  HTTOP=12  HTTOPLEFT=13
  HTTOPRIGHT=14  HTBOTTOM=15  HTBOTTOMLEFT=16  HTBOTTOMRIGHT=17  HTCAPTION=2
只要四边四角仍返回 1x，缩放就没坏。
"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

sys.path.insert(0, ".")

user32 = ctypes.windll.user32

user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.restype = ctypes.c_ssize_t
user32.IsZoomed.argtypes = [wintypes.HWND]
user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.MonitorFromWindow.restype = wintypes.HMONITOR
user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.c_void_p]

WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084
GWLP_WNDPROC = -4
MONITOR_DEFAULTTONEAREST = 2

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

WNDPROCTYPE = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                                 wintypes.WPARAM, wintypes.LPARAM)


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


class NCCALCSIZE_PARAMS(ctypes.Structure):
    _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]


CODES = {0: "HTNOWHERE", 1: "HTCLIENT", 2: "HTCAPTION", 10: "HTLEFT", 11: "HTRIGHT",
         12: "HTTOP", 13: "HTTOPLEFT", 14: "HTTOPRIGHT", 15: "HTBOTTOM",
         16: "HTBOTTOMLEFT", 17: "HTBOTTOMRIGHT"}


class Frame:
    def __init__(self, hwnd):
        self.hwnd = hwnd
        self.old = int(GetWndProc(wintypes.HWND(hwnd), GWLP_WNDPROC))
        self._proc = WNDPROCTYPE(self._wndproc)
        SetWndProc(wintypes.HWND(hwnd), GWLP_WNDPROC,
                   ctypes.cast(self._proc, ctypes.c_void_p).value)

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_NCCALCSIZE and wparam:
            if user32.IsZoomed(wintypes.HWND(hwnd)):
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


def hit(hwnd, x, y):
    lp = (y & 0xFFFF) << 16 | (x & 0xFFFF)
    code = int(user32.SendMessageW(wintypes.HWND(hwnd), WM_NCHITTEST, 0, lp))
    return CODES.get(code, f"?{code}")


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

    r = wintypes.RECT()
    user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(r))

    def report(label):
        r2 = wintypes.RECT()
        user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(r2))
        l, t, rr, b = r2.left, r2.top, r2.right, r2.bottom
        mx, my = (l + rr) // 2, (t + b) // 2
        print(f"{label} 窗口=({l},{t})-({rr},{b})")
        pts = {
            "左边 2px": (l + 2, my), "右边 2px": (rr - 3, my),
            "上边 2px": (mx, t + 2), "下边 2px": (mx, b - 3),
            "左上角": (l + 2, t + 2), "右上角": (rr - 3, t + 2),
            "左下角": (l + 2, b - 3), "右下角": (rr - 3, b - 3),
            "顶栏中间": (mx, t + 24), "内容区": (mx, my),
        }
        for k, (x, y) in pts.items():
            print(f"   {k:8s} ({x},{y}) -> {hit(hwnd, x, y)}")

    report("未改 NCCALCSIZE")
    f = Frame(hwnd)
    user32.SetWindowPos(wintypes.HWND(hwnd), None, 0, 0, 0, 0,
                        0x0001 | 0x0002 | 0x0004 | 0x0020 | 0x0040)
    settle(1.0)
    report("已截 NCCALCSIZE")

    f.restore()
    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
