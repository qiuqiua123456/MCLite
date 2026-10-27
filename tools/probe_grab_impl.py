"""对比两种抓屏实现：GetDIBits（现状）vs CreateDIBSection（直接画进内存）。

现象：`grab()` 实测 200x200 与 929x701 都是 ~260 ms —— 耗时与尺寸无关，
说明是每次调用的固定开销，最可疑的是 `GetDIBits`（要 GDI 把 DDB 重新
逐行转成 DIB）。CreateDIBSection 让我们一开始就有一块自己的内存，
BitBlt 直接写进去，连 GetDIBits 都不用调。

用法：python tools/probe_grab_impl.py
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
kernel32 = ctypes.windll.kernel32

BI_RGB = 0
DIB_RGB_COLORS = 0
SRCCOPY = 0x00CC0020
CAPTUREBLT = 0x40000000

gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                         ctypes.c_int, wintypes.HDC, ctypes.c_int, ctypes.c_int,
                         wintypes.DWORD]
gdi32.BitBlt.restype = wintypes.BOOL
gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
                                   ctypes.POINTER(ctypes.c_void_p),
                                   wintypes.HANDLE, wintypes.DWORD]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]


class BIH(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BI(ctypes.Structure):
    _fields_ = [("bmiHeader", BIH), ("bmiColors", wintypes.DWORD * 3)]


def grab_dibsection(x, y, w, h):
    screen = user32.GetDC(None)
    if not screen:
        return None
    mem = gdi32.CreateCompatibleDC(screen)
    info = BI()
    info.bmiHeader.biSize = ctypes.sizeof(BIH)
    info.bmiHeader.biWidth = w
    info.bmiHeader.biHeight = -h
    info.bmiHeader.biPlanes = 1
    info.bmiHeader.biBitCount = 32
    info.bmiHeader.biCompression = BI_RGB
    bits = ctypes.c_void_p()
    bmp = gdi32.CreateDIBSection(screen, ctypes.byref(info), DIB_RGB_COLORS,
                                 ctypes.byref(bits), None, 0)
    if not bmp or not bits:
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(None, screen)
        return None
    old = gdi32.SelectObject(mem, bmp)
    try:
        gdi32.BitBlt(mem, 0, 0, w, h, screen, x, y, SRCCOPY)
        return ctypes.string_at(bits, w * h * 4)
    finally:
        gdi32.SelectObject(mem, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(None, screen)


def grab_ppm(raw, w, h):
    out = bytearray(w * h * 3)
    out[0::3] = raw[2::4]
    out[1::3] = raw[1::4]
    out[2::3] = raw[0::4]
    return b"P6\n%d %d\n255\n" % (w, h) + bytes(out)


def main() -> None:
    from mclite.ui import grab as old

    cases = ((0, 0, 200, 200), (0, 0, 929, 701))
    for (x, y, w, h) in cases:
        print(f"--- {w}x{h} at {x},{y}")
        for label, fn in (("GetDIBits", old.grab),
                          ("DIBSection", grab_dibsection)):
            ts = []
            for _ in range(5):
                t = time.perf_counter()
                raw = fn(x, y, w, h)
                ts.append((time.perf_counter() - t) * 1000.0)
            ok = raw is not None and len(raw) == w * h * 4
            print(f"  {label:11s} " + ", ".join(f"{v:6.1f}" for v in ts)
                  + f"  bytes_ok={ok}")

        t = time.perf_counter()
        raw = grab_dibsection(x, y, w, h)
        ppm = grab_ppm(raw, w, h)
        t2 = time.perf_counter()
        print(f"  DIB+PPM      {(t2 - t) * 1000:6.1f} ms  ({len(ppm)} bytes)")


if __name__ == "__main__":
    main()
