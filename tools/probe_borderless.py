"""探针 v2：和正式程序一样先设 DPI 感知，再验证无标题栏窗口的行为。

要回答的问题：
1. 去 caption 后客户区尺寸会不会变大、最大化是否溢出工作区；
2. 最大化 -> 还原 一圈后客户区尺寸是否原样恢复（无边框窗口最常见的坑：
   最大化时 Tk 把 geometry 记成屏幕尺寸，还原后窗口变得比原来大）；
3. 最小化再用任务栏还原、以及从最大化直接关闭，是否留下怪状态。
"""
from __future__ import annotations

import ctypes
import time
import tkinter as tk
from ctypes import wintypes

user32 = ctypes.windll.user32
GWL_STYLE = -16
WS_CAPTION = 0x00C00000
SPI_GETWORKAREA = 0x0030
SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE, SWP_FRAMECHANGED = 0x1, 0x2, 0x4, 0x10, 0x20

_get = user32.GetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user32.GetWindowLongW
_set = user32.SetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user32.SetWindowLongW
_get.restype = ctypes.c_ssize_t
_set.restype = ctypes.c_ssize_t


def hwnd_of(root: tk.Tk) -> int:
    return user32.GetParent(root.winfo_id()) or root.winfo_id()


def work_area():
    rc = wintypes.RECT()
    user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rc), 0)
    return rc.left, rc.top, rc.right, rc.bottom


def client_rect(hwnd):
    rc = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rc))
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    return pt.x, pt.y, pt.x + rc.right, pt.y + rc.bottom


def strip_caption(root):
    hwnd = hwnd_of(root)
    st = _get(hwnd, GWL_STYLE)
    _set(hwnd, GWL_STYLE, st & ~WS_CAPTION)
    user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                        SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)
    return hwnd


def pump(root, sec=0.45):
    end = time.time() + sec
    while time.time() < end:
        root.update()
        time.sleep(0.02)


def main() -> int:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    root = tk.Tk()
    root.title("probe2")
    root.geometry("1160x724+120+80")
    root.minsize(880, 560)
    tk.Frame(root, bg="#2D6FB8", height=48).pack(fill="x")
    tk.Frame(root, bg="#F2F5F9").pack(fill="both", expand=True)
    pump(root, 0.5)

    hwnd = strip_caption(root)
    pump(root)
    print(f"1) 去 caption 后 client={client_rect(hwnd)}  root={root.winfo_width()}x{root.winfo_height()}")

    base = client_rect(hwnd)
    base_w, base_h = base[2] - base[0], base[3] - base[1]

    # ---- 最大化
    root.state("zoomed")
    pump(root, 0.6)
    cl = client_rect(hwnd)
    wa = work_area()
    print(f"2) 最大化 client={cl} work={wa} "
          f"overhang={(cl[0]-wa[0], cl[1]-wa[1], cl[2]-wa[2], cl[3]-wa[3])}")
    print(f"   tk 记录尺寸={root.winfo_width()}x{root.winfo_height()} geometry={root.geometry()}")

    # ---- 还原
    root.state("normal")
    pump(root, 0.6)
    rest = client_rect(hwnd)
    rw, rh = rest[2] - rest[0], rest[3] - rest[1]
    print(f"3) 还原 client={rest} 尺寸={rw}x{rh} (原 {base_w}x{base_h}) "
          f"geometry={root.geometry()}")

    # ---- 第二次最大化 -> 还原（连续切换是否漂移）
    for i in range(2):
        root.state("zoomed")
        pump(root, 0.35)
        root.state("normal")
        pump(root, 0.35)
        r = client_rect(hwnd)
        print(f"4.{i}) 二次往返后尺寸={r[2]-r[0]}x{r[3]-r[1]} geometry={root.geometry()}")

    # ---- 最小化 -> 还原
    root.iconify()
    pump(root, 0.4)
    root.deiconify()
    pump(root, 0.5)
    r = client_rect(hwnd)
    print(f"5) 最小化往返后尺寸={r[2]-r[0]}x{r[3]-r[1]} state={root.state()}")

    root.destroy()
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
