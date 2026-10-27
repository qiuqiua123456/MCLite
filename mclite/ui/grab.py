"""把屏幕上一块矩形抓成位图（纯 ctypes + GDI，不依赖 PIL）。

用途只有一个：拉伸窗口期间给页面做一张「像素快照」顶替真实控件树，让
Windows 重绘时只需要 blit 一张图，而不是重绘页面里那上百个子窗口。

为什么不用 PIL 的 ImageGrab：那条路走 GDI+ 并且每次都要新建 canvas，
实测 713ms（首次更慢）；这里用桌面 DC + ``BitBlt`` 约 260ms —— 仍然是本机
最便宜的一条路（``GetDC(hwnd)`` + BitBlt 只要 2 ms，但抓到的是未合成的
窗口 DC 内容，和屏幕像素对不上，不能用），所以调用方要保证别频繁调。
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

__all__ = ["grab", "grab_ppm", "available"]

_gdi32 = ctypes.windll.gdi32
_user32 = ctypes.windll.user32


class _BITMAPINFOHEADER(ctypes.Structure):
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


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER),
                ("bmiColors", wintypes.DWORD * 3)]


# ⚠ 签名必须写死：默认 restype 是 32 位 int，64 位下 HDC/HBITMAP 会被截断，
# 拿到坏句柄再调 GDI 就是 0xC0000005（进程无声退出）。
_gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
_gdi32.CreateCompatibleDC.restype = wintypes.HDC
_gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
_gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
_gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
_gdi32.SelectObject.restype = wintypes.HGDIOBJ
_gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
_gdi32.DeleteDC.argtypes = [wintypes.HDC]
_gdi32.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                          ctypes.c_int, wintypes.HDC, ctypes.c_int, ctypes.c_int,
                          wintypes.DWORD]
_gdi32.BitBlt.restype = wintypes.BOOL
_gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT,
                             wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p,
                             wintypes.UINT]
_gdi32.GetDIBits.restype = ctypes.c_int
_user32.GetDC.argtypes = [wintypes.HWND]
_user32.GetDC.restype = wintypes.HDC
_user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]

_SRCCOPY = 0x00CC0020


def available() -> bool:
    return hasattr(ctypes, "windll")


def grab(x: int, y: int, w: int, h: int) -> bytes | None:
    """抓屏幕 (x, y) 起 w×h 的像素，返回 BGRA 原始字节（行序自上而下）。"""
    if w <= 0 or h <= 0:
        return None
    screen = _user32.GetDC(None)
    if not screen:
        return None
    mem = _gdi32.CreateCompatibleDC(screen)
    bmp = _gdi32.CreateCompatibleBitmap(screen, w, h)
    old = _gdi32.SelectObject(mem, bmp)
    try:
        _gdi32.BitBlt(mem, 0, 0, w, h, screen, x, y, _SRCCOPY)
        info = _BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        info.bmiHeader.biWidth = w
        info.bmiHeader.biHeight = -h          # 负数 = 自上而下
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = 0      # BI_RGB
        buf = ctypes.create_string_buffer(w * h * 4)
        if _gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(info), 0) == 0:
            return None
        return buf.raw
    finally:
        _gdi32.SelectObject(mem, old)
        _gdi32.DeleteObject(bmp)
        _gdi32.DeleteDC(mem)
        _user32.ReleaseDC(None, screen)


def _bgra_to_ppm(raw: bytes, w: int, h: int) -> bytes:
    """BGRA → RGB，再包成 PPM(P6) 头。切片赋值比逐像素循环快一个量级。"""
    out = bytearray(w * h * 3)
    out[0::3] = raw[2::4]        # R
    out[1::3] = raw[1::4]        # G
    out[2::3] = raw[0::4]        # B
    return b"P6\n%d %d\n255\n" % (w, h) + bytes(out)


def grab_ppm(x: int, y: int, w: int, h: int) -> bytes | None:
    """抓图并直接返回 PPM(P6) 字节，可直接喂给 ``tk.PhotoImage(format="ppm")``。

    成本实测（本机，且**与抓图尺寸无关**）：``BitBlt`` 260 ms + 转 PPM 3.3 ms
    + 建 ``PhotoImage`` 1.7 ms ≈ 265 ms。慢的是「从桌面 DC 读像素」这一步
    —— 200x200 和 929x701 一样是 260 ms，`CreateDIBSection` 也救不了
    （`tools/probe_grab_impl.py` 对比过）。所以**只在真的拖动时调它**：
    `App._on_container_configure` 里只有连着第二个 `<Configure>` 才拍快照。
    """
    raw = grab(x, y, w, h)
    if raw is None:
        return None
    return _bgra_to_ppm(raw, w, h)
