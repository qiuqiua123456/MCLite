"""探针：确认自实现 WM_NCHITTEST 之后，真实鼠标能不能缩放窗口。

上一版用 mouse_event 模拟拖动没生效，怀疑是窗口没有前台激活（DefWindowProc
只在活动窗口上启动尺寸循环）。这里先 SetForegroundWindow + 点击激活，再拖，
并额外用 WM_NCLBUTTONDOWN/HTRIGHT 直接请求起始尺寸循环做交叉验证。
"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

sys.path.insert(0, ".")

user32 = ctypes.windll.user32

user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
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
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.restype = ctypes.c_ssize_t
user32.IsZoomed.argtypes = [wintypes.HWND]
user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.MonitorFromWindow.restype = wintypes.HMONITOR
user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.c_void_p]

WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084
WM_NCLBUTTONDOWN = 0x00A1
GWLP_WNDPROC = -4
MONITOR_DEFAULTTONEAREST = 2
HTCLIENT, HTLEFT, HTRIGHT, HTTOP = 1, 10, 11, 12
HTTOPLEFT, HTTOPRIGHT, HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 13, 14, 15, 16, 17
SIZE_EDGE = 6
CODES = {0: "HTNOWHERE", 1: "HTCLIENT", 2: "HTCAPTION", 10: "HTLEFT", 11: "HTRIGHT",
         12: "HTTOP", 13: "HTTOPLEFT", 14: "HTTOPRIGHT", 15: "HTBOTTOM",
         16: "HTBOTTOMLEFT", 17: "HTBOTTOMRIGHT"}

WNDPROCTYPE = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                                 wintypes.WPARAM, wintypes.LPARAM)


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


class NCCALCSIZE_PARAMS(ctypes.Structure):
    _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]


def resize_code(hwnd, sx, sy):
    r = wintypes.RECT()
    user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(r))
    e = SIZE_EDGE
    left, right = sx < r.left + e, sx >= r.right - e
    top, bottom = sy < r.top + e, sy >= r.bottom - e
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
        if msg == WM_NCHITTEST and not user32.IsZoomed(wintypes.HWND(hwnd)):
            lp = int(lparam) & 0xFFFFFFFF
            sx, sy = lp & 0xFFFF, (lp >> 16) & 0xFFFF
            if sx >= 0x8000:
                sx -= 0x10000
            if sy >= 0x8000:
                sy -= 0x10000
            code = resize_code(hwnd, sx, sy)
            if code != HTCLIENT:
                return code
        return user32.CallWindowProcW(ctypes.c_void_p(self.old), wintypes.HWND(hwnd),
                                      msg, wparam, lparam)

    def restore(self):
        if self.old:
            SetWndProc(wintypes.HWND(self.hwnd), GWLP_WNDPROC, self.old)
            self.old = 0


def rect(hwnd):
    r = wintypes.RECT()
    user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


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

    def settle(sec=0.7):
        end = time.time() + sec
        while time.time() < end:
            app.update()
            time.sleep(0.02)

    settle(1.2)
    hwnd = frameless.hwnd_of(app)
    user32.SetForegroundWindow(wintypes.HWND(hwnd))
    user32.SetCursorPos(600, 184)
    settle(0.4)

    f = Frame(hwnd)
    user32.SetWindowPos(wintypes.HWND(hwnd), None, 0, 0, 0, 0,
                        0x0001 | 0x0002 | 0x0004 | 0x0020 | 0x0040)
    settle(1.0)
    before = rect(hwnd)
    print(f"起始 {before}")

    # ---- 方式 1：真实鼠标拖右边框
    l, t, r, b = before
    my = (t + b) // 2
    print("\n方式1：真实鼠标拖右边框 +70px")
    user32.SetCursorPos(r - 2, my)
    settle(0.3)
    user32.mouse_event(0x0002, 0, 0, 0, 0)          # LEFTDOWN
    settle(0.25)
    for _ in range(7):
        user32.mouse_event(0x0001, 10, 0, 0, 0)     # MOVE
        settle(0.06)
    user32.mouse_event(0x0004, 0, 0, 0, 0)          # LEFTUP
    settle(0.7)
    after = rect(hwnd)
    print(f"  {before} -> {after}   宽 {before[2]-before[0]} -> {after[2]-after[0]}")
    works_mouse = after[2] - after[0] > (before[2] - before[0]) + 20

    # ---- 方式 2：直接请求起始尺寸循环
    print("\n方式2：WM_NCLBUTTONDOWN / HTRIGHT（程序化请求尺寸循环）")
    b2 = rect(hwnd)
    user32.SetCursorPos(b2[2] - 2, my)
    settle(0.2)
    user32.SendMessageW(wintypes.HWND(hwnd), WM_NCLBUTTONDOWN, HTRIGHT, 0)
    settle(0.3)
    for _ in range(7):
        user32.mouse_event(0x0001, -10, 0, 0, 0)
        settle(0.06)
    settle(0.5)
    a2 = rect(hwnd)
    print(f"  {b2} -> {a2}   宽 {b2[2]-b2[0]} -> {a2[2]-a2[0]}")
    works_loop = a2[2] - a2[0] < (b2[2] - b2[0]) - 20

    print(f"\n真实鼠标拖动可缩放: {works_mouse}")
    print(f"尺寸循环可启动:     {works_loop}")

    f.restore()
    app.destroy()
    return 0 if works_mouse or works_loop else 1


if __name__ == "__main__":
    raise SystemExit(main())
