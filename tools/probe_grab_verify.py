"""验证「窗口 DC BitBlt」与「桌面 DC BitBlt」抓出来的像素是否一致。

`probe_grab_window.py` 显示：桌面 DC 抓图固定 260 ms（与尺寸无关），
而 `GetDC(hwnd)` + BitBlt 只要 2.3 ms —— 差 100 倍。后者抓的是窗口自己
的客户区，我们要的正是这个。这里逐像素比对两者，确认可以替换。

注意坐标系：窗口 DC 的原点是**窗口**左上角（含 7px 无边框缩放边框），
客户区偏移要靠 GetClientRect + ClientToScreen 算出来。

用法：python tools\probe_grab_verify.py
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

gdi32 = ctypes.windll.gdi32
user32 = ctypes.windll.user32

SRCCOPY = 0x00CC0020
BI_RGB = 0
DIB_RGB_COLORS = 0

gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
                                   ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE,
                                   wintypes.DWORD]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                         ctypes.c_int, wintypes.HDC, ctypes.c_int, ctypes.c_int,
                         wintypes.DWORD]
gdi32.BitBlt.restype = wintypes.BOOL
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]


class BIH(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BI(ctypes.Structure):
    _fields_ = [("bmiHeader", BIH), ("bmiColors", wintypes.DWORD * 3)]


def _grab_raw(src_dc, src_x, src_y, w, h):
    mem = gdi32.CreateCompatibleDC(src_dc)
    info = BI()
    info.bmiHeader.biSize = ctypes.sizeof(BIH)
    info.bmiHeader.biWidth = w
    info.bmiHeader.biHeight = -h
    info.bmiHeader.biPlanes = 1
    info.bmiHeader.biBitCount = 32
    info.bmiHeader.biCompression = BI_RGB
    bits = ctypes.c_void_p()
    bmp = gdi32.CreateDIBSection(src_dc, ctypes.byref(info), DIB_RGB_COLORS,
                                 ctypes.byref(bits), None, 0)
    old = gdi32.SelectObject(mem, bmp)
    try:
        gdi32.BitBlt(mem, 0, 0, w, h, src_dc, src_x, src_y, SRCCOPY)
        return ctypes.string_at(bits, w * h * 4)
    finally:
        gdi32.SelectObject(mem, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem)


def grab_by_window(hwnd, w, h, src_x=0, src_y=0):
    """从窗口 DC 抓一块，(src_x, src_y) 相对**客户区**左上角。"""
    src = user32.GetDC(hwnd)
    if not src:
        return None
    try:
        return _grab_raw(src, src_x, src_y, w, h)
    finally:
        user32.ReleaseDC(hwnd, src)


def grab_by_screen(x, y, w, h):
    src = user32.GetDC(None)
    if not src:
        return None
    try:
        return _grab_raw(src, x, y, w, h)
    finally:
        user32.ReleaseDC(None, src)


def main() -> None:
    from mclite.ui.app import App

    app = App()
    app.update()
    app.create_pages()
    app.show_page("home")
    end = time.time() + 2.0
    while time.time() < end:
        app.update()
        time.sleep(0.01)

    page = app._pages["home"]
    hwnd = user32.GetAncestor(page.winfo_id(), 2)
    x, y = page.winfo_rootx(), page.winfo_rooty()
    w, h = page.winfo_width(), page.winfo_height()
    print(f"page {w}x{h} at {x},{y}  hwnd={hwnd}")

    for label, fn in (("screen", lambda: grab_by_screen(x, y, w, h)),
                      ("window", lambda: grab_by_window(hwnd, w, h,
                                                        x - app.winfo_rootx(),
                                                        y - app.winfo_rooty()))):
        ts = []
        raw = None
        for _ in range(5):
            t = time.perf_counter()
            raw = fn()
            ts.append((time.perf_counter() - t) * 1000.0)
        print(f"  {label:7s} " + ", ".join(f"{v:6.1f}" for v in ts))

    a = grab_by_screen(x, y, w, h)
    b = grab_by_window(hwnd, w, h, x - app.winfo_rootx(), y - app.winfo_rooty())
    diff = sum(1 for i in range(0, len(a), 4) if a[i:i + 4] != b[i:i + 4])
    total = len(a) // 4
    print(f"  逐像素差异 {diff}/{total} = {diff / total * 100:.3f}%")
    # 差异位置分布（如果是整体错位，差异会集中在边缘）
    ys = {}
    for i in range(0, len(a), 4):
        if a[i:i + 4] != b[i:i + 4]:
            row = (i // 4) // w
            ys[row] = ys.get(row, 0) + 1
    top = sorted(ys.items(), key=lambda kv: -kv[1])[:6]
    print(f"  差异最多的行: {top}")
    app.destroy()


if __name__ == "__main__":
    main()
