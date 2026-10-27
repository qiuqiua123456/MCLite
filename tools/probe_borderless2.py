"""探针 v3：验证「去 caption 之后怎么拖窗口」。

方案 A（首选）：在顶栏空白处按下鼠标时，自己往窗口发 WM_NCLBUTTONDOWN(HTCAPTION)，
让系统接管拖动 —— 这样贴边吸附 / 拖动到顶部最大化全都免费保留，且不需要
在 Python 里 subclass WndProc（那种做法要自己跟 Tk 抢消息，容易崩）。

同时确认三件事：
1. 去 caption 后 DWM 还画不画阴影、圆角（Win11）；
2. SendMessage(WM_NCLBUTTONDOWN) 之后窗口位置真的跟着鼠标走；
3. 自绘的最小化/最大化/关闭按钮调用 Tk 的 iconify/state/destroy 是否正常。
"""
from __future__ import annotations

import ctypes
import time
import tkinter as tk
from ctypes import wintypes

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi
GWL_STYLE = -16
WS_CAPTION = 0x00C00000
SPI_GETWORKAREA = 0x0030
SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE, SWP_FRAMECHANGED = 0x1, 0x2, 0x4, 0x10, 0x20
WM_NCLBUTTONDOWN = 0x00A1
HTCAPTION = 2

_get = user32.GetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user32.GetWindowLongW
_set = user32.SetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user32.SetWindowLongW
_get.restype = ctypes.c_ssize_t
_set.restype = ctypes.c_ssize_t


def hwnd_of(root):
    return user32.GetParent(root.winfo_id()) or root.winfo_id()


def pump(root, sec=0.4):
    end = time.time() + sec
    while time.time() < end:
        root.update()
        time.sleep(0.02)


def start_window_drag(hwnd: int) -> None:
    """让系统接管这次拖动（= 抓住标题栏拖动），保留贴边吸附。"""
    user32.ReleaseCapture()
    user32.SendMessageW(hwnd, WM_NCLBUTTONDOWN, HTCAPTION, 0)


def win_rect(hwnd):
    rc = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rc))
    return rc.left, rc.top, rc.right, rc.bottom


def main() -> int:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    root = tk.Tk()
    root.geometry("1160x724+140+100")
    root.minsize(880, 560)
    bar = tk.Frame(root, bg="#2D6FB8", height=48)
    bar.pack(fill="x")
    tk.Frame(root, bg="#F2F5F9").pack(fill="both", expand=True)
    pump(root, 0.5)

    hwnd = hwnd_of(root)
    st = _get(hwnd, GWL_STYLE)
    _set(hwnd, GWL_STYLE, st & ~WS_CAPTION)
    user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                        SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)
    pump(root, 0.6)

    # ---- DWM 状态：阴影 / 圆角
    # DWMWA_NCRENDERING_POLICY=2(1=禁用,2=启用), 33=DWMWA_WINDOW_CORNER_PREFERENCE
    val = ctypes.c_int(0)
    hr = dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), 33, ctypes.byref(val), ctypes.sizeof(val))
    print(f"DWMWA_WINDOW_CORNER_PREFERENCE hr=0x{hr & 0xFFFFFFFF:08X} value={val.value} (1=不圆角 2=圆角 3=小圆角)")
    ext = wintypes.RECT()
    hr2 = dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), 9, ctypes.byref(ext), ctypes.sizeof(ext))
    print(f"DWMWA_EXTENDED_FRAME_BOUNDS hr=0x{hr2 & 0xFFFFFFFF:08X} rect={ext.left},{ext.top},{ext.right},{ext.bottom}")
    wr = win_rect(hwnd)
    print(f"GetWindowRect = {wr}  -> 有无阴影边距: left={ext.left-wr[0]} right={wr[2]-ext.right}")

    # ---- 模拟拖动：把窗口挪到 300,200，再用 NCLBUTTONDOWN 让系统接管，
    #      然后用绝对坐标鼠标事件推动（SendInput 会真动鼠标，这里只验证
    #      「有没有进入系统拖动状态」，所以查 GetCapture 与光标状态）
    before = win_rect(hwnd)
    start_window_drag(hwnd)
    pump(root, 0.2)
    cap = user32.GetCapture()
    print(f"拖动前 rect={before}  拖动中 GetCapture={cap} (非 0 = 系统已接管拖动)")
    if cap:
        user32.SendMessageW(cap, 0x0202, 0, 0)         # WM_LBUTTONUP 结束拖动
    pump(root, 0.2)
    after = win_rect(hwnd)
    print(f"拖动后 rect={after}  capture 已释放={user32.GetCapture() == 0}")

    # ---- 自绘按钮动作
    root.iconify()
    pump(root, 0.4)
    print(f"最小化后 state={root.state()}")
    root.deiconify()
    pump(root, 0.4)
    print(f"还原后 state={root.state()}")
    root.state("zoomed")
    pump(root, 0.5)
    print(f"最大化 state={root.state()} size={root.winfo_width()}x{root.winfo_height()}")
    root.state("normal")
    pump(root, 0.5)
    print(f"还原 state={root.state()} size={root.winfo_width()}x{root.winfo_height()}")

    root.destroy()
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
