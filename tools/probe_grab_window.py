"""找出「抓我们自己的窗口」最便宜的路。

`grab()` 慢在 `BitBlt` 本身：实测 200x200 与 929x701 都是 260 ms，且
`GetDC/BitBlt` 之外每步都是 0 ms。也就是说「从桌面 DC 读像素」在这台机器
上就是 260 ms（DWM 合成 + 驱动路径），跟尺寸无关。

既然要抓的是我们**自己的窗口**，还有两条更便宜的路：
  A. `GetDC(hwnd)` 拿窗口 DC 再 BitBlt（不经桌面合成）
  B. `PrintWindow(hwnd, mem, PW_RENDERFULLCONTENT)` 让窗口自己画出内容

用法：python tools/probe_grab_window.py [w] [h]
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
PW_RENDERFULLCONTENT = 0x00000002
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
user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
user32.PrintWindow.restype = wintypes.BOOL
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND


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


def _setup(src_dc, w, h):
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
    return mem, bmp, bits, old


def _teardown(mem, bmp, old):
    gdi32.SelectObject(mem, old)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)


def grab_window_dc(hwnd, w, h):
    src = user32.GetDC(hwnd)
    if not src:
        return None
    mem, bmp, bits, old = _setup(src, w, h)
    try:
        gdi32.BitBlt(mem, 0, 0, w, h, src, 0, 0, SRCCOPY)
        return ctypes.string_at(bits, w * h * 4)
    finally:
        _teardown(mem, bmp, old)
        user32.ReleaseDC(hwnd, src)


def grab_printwindow(hwnd, w, h):
    src = user32.GetDC(hwnd)
    mem, bmp, bits, old = _setup(src, w, h)
    try:
        user32.PrintWindow(hwnd, mem, PW_RENDERFULLCONTENT)
        return ctypes.string_at(bits, w * h * 4)
    finally:
        _teardown(mem, bmp, old)
        user32.ReleaseDC(hwnd, src)


def main() -> None:
    import tkinter as tk

    from mclite.ui import grab as screen_grab

    root = tk.Tk()
    root.geometry("1000x700+80+80")
    cv = tk.Canvas(root, bg="#2b6cb0", highlightthickness=0)
    cv.pack(fill="both", expand=True)
    for i in range(0, 1000, 40):
        cv.create_line(i, 0, 1000 - i, 700, fill="#a0c4e8")
    root.update()
    root.update_idletasks()
    time.sleep(0.5)
    root.update()

    hwnd = user32.GetAncestor(root.winfo_id(), 2)   # GA_ROOT
    w = root.winfo_width()
    h = root.winfo_height()
    print(f"hwnd={hwnd} size={w}x{h}")

    cases = (
        ("screen BitBlt", lambda: screen_grab.grab(root.winfo_rootx(),
                                                   root.winfo_rooty(), w, h)),
        ("windowDC BitBlt", lambda: grab_window_dc(hwnd, w, h)),
        ("PrintWindow", lambda: grab_printwindow(hwnd, w, h)),
    )
    for label, fn in cases:
        ts = []
        raw = None
        for _ in range(6):
            t = time.perf_counter()
            raw = fn()
            ts.append((time.perf_counter() - t) * 1000.0)
        # 取中心像素判断是不是真抓到了内容（应该接近 #2b6cb0 = (43,108,176)）
        px = None
        if raw:
            i = ((h // 2) * w + w // 2) * 4
            px = (raw[i + 2], raw[i + 1], raw[i])
        print(f"  {label:16s} " + ", ".join(f"{v:6.1f}" for v in ts)
              + f"  中心像素={px}")
    root.destroy()


if __name__ == "__main__":
    main()
