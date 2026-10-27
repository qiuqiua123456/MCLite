"""探针：截 NCCALCSIZE 后自己实现 WM_NCHITTEST，把八向缩放热区补回来。

系统原始实现（Tk 的 WndProc → DefWindowProc）在客户区吃掉后只会返回
HTCLIENT，所以缩放必须自己算：距窗口边缘 6px 内按方位返回 HTLEFT/HTTOP/…，
其余交给原来的 WndProc。最大化时不能返回缩放码（否则拖不动），返回 HTCLIENT。
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

HTCLIENT, HTLEFT, HTRIGHT, HTTOP, HTTOPLEFT, HTTOPRIGHT = 1, 10, 11, 12, 13, 14
HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 15, 16, 17

GWL_STYLE = -16
WS_THICKFRAME = 0x00040000
SIZE_EDGE = 6

CODES = {0: "HTNOWHERE", 1: "HTCLIENT", 2: "HTCAPTION", 10: "HTLEFT", 11: "HTRIGHT",
         12: "HTTOP", 13: "HTTOPLEFT", 14: "HTTOPRIGHT", 15: "HTBOTTOM",
         16: "HTBOTTOMLEFT", 17: "HTBOTTOMRIGHT"}


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


class NCCALCSIZE_PARAMS(ctypes.Structure):
    _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]


def resize_code(hwnd, sx, sy):
    r = wintypes.RECT()
    user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(r))
    e = SIZE_EDGE
    left = sx < r.left + e
    right = sx >= r.right - e
    top = sy < r.top + e
    bottom = sy >= r.bottom - e
    if top and left:
        return HTTOPLEFT
    if top and right:
        return HTTOPRIGHT
    if bottom and left:
        return HTBOTTOMLEFT
    if bottom and right:
        return HTBOTTOMRIGHT
    if left:
        return HTLEFT
    if right:
        return HTRIGHT
    if top:
        return HTTOP
    if bottom:
        return HTBOTTOM
    return HTCLIENT


class Frame:
    def __init__(self, hwnd):
        self.hwnd = hwnd
        self.old = int(GetWndProc(wintypes.HWND(hwnd), GWLP_WNDPROC))
        self.calls = {"nccalc": 0, "hit": 0, "resize": 0}
        self._proc = WNDPROCTYPE(self._wndproc)
        SetWndProc(wintypes.HWND(hwnd), GWLP_WNDPROC,
                   ctypes.cast(self._proc, ctypes.c_void_p).value)

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_NCCALCSIZE and wparam:
            self.calls["nccalc"] += 1
            if user32.IsZoomed(wintypes.HWND(hwnd)):
                params = ctypes.cast(lparam, ctypes.POINTER(NCCALCSIZE_PARAMS))
                mi = MONITORINFO()
                mi.cbSize = ctypes.sizeof(MONITORINFO)
                mon = user32.MonitorFromWindow(wintypes.HWND(hwnd), MONITOR_DEFAULTTONEAREST)
                user32.GetMonitorInfoW(mon, ctypes.byref(mi))
                params.contents.rgrc[0] = mi.rcWork
            return 0
        if msg == WM_NCHITTEST:
            self.calls["hit"] += 1
            if not user32.IsZoomed(wintypes.HWND(hwnd)):
                lp = int(lparam) & 0xFFFFFFFF
                sx = lp & 0xFFFF
                sy = (lp >> 16) & 0xFFFF
                if sx >= 0x8000:
                    sx -= 0x10000
                if sy >= 0x8000:
                    sy -= 0x10000
                code = resize_code(hwnd, sx, sy)
                if code != HTCLIENT:
                    self.calls["resize"] += 1
                    return code
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
    f = Frame(hwnd)
    user32.SetWindowPos(wintypes.HWND(hwnd), None, 0, 0, 0, 0,
                        0x0001 | 0x0002 | 0x0004 | 0x0020 | 0x0040)
    settle(1.0)

    r = wintypes.RECT()
    user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(r))
    l, t, rr, b = r.left, r.top, r.right, r.bottom
    mx, my = (l + rr) // 2, (t + b) // 2
    print(f"窗口=({l},{t})-({rr},{b})")
    pts = {
        "左边 2px": (l + 2, my), "右边 2px": (rr - 3, my),
        "上边 2px": (mx, t + 2), "下边 2px": (mx, b - 3),
        "左上角": (l + 2, t + 2), "右上角": (rr - 3, t + 2),
        "左下角": (l + 2, b - 3), "右下角": (rr - 3, b - 3),
        "顶栏中间": (mx, t + 24), "内容区": (mx, my),
        "关闭按钮": (rr - 24, t + 24),
    }
    for k, (x, y) in pts.items():
        print(f"   {k:8s} ({x},{y}) -> {hit(hwnd, x, y)}")
    print("调用计数:", f.calls)

    # 真实拖一下右边框验证能不能缩放
    before = wintypes.RECT()
    user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(before))
    print("\n用真实鼠标事件拖右边框（+80px）…")
    user32.SetCursorPos(rr - 2, my)
    settle(0.2)
    user32.mouse_event(0x0002, 0, 0, 0, 0)          # LEFTDOWN
    settle(0.2)
    user32.mouse_event(0x0001, 80, 0, 0, 0)         # MOVE
    settle(0.3)
    user32.mouse_event(0x0004, 0, 0, 0, 0)          # LEFTUP
    settle(0.6)
    after = wintypes.RECT()
    user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(after))
    print(f"  缩放前宽={before.right - before.left}  缩放后宽={after.right - after.left}")

    f.restore()
    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
