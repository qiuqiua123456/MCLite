"""探针 v4：去 caption 之后，窗口四周会剩一条非客户区（缩放边框）。

它到底可不可见？用「客户区涂洋红 + 顶栏蓝」的窗口截一张图，肉眼判读。
两种做法对比：
  A. 只去 WS_CAPTION
  B. 去 WS_CAPTION + 接管 WM_NCCALCSIZE（客户区 = 整个窗口）
"""
from __future__ import annotations

import ctypes
import time
import tkinter as tk
from ctypes import wintypes

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
GWL_STYLE = -16
WS_CAPTION = 0x00C00000
SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE, SWP_FRAMECHANGED = 0x1, 0x2, 0x4, 0x10, 0x20

_get = user32.GetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user32.GetWindowLongW
_set = user32.SetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user32.SetWindowLongW
_get.restype = ctypes.c_ssize_t
_set.restype = ctypes.c_ssize_t


def hwnd_of(root):
    return user32.GetParent(root.winfo_id()) or root.winfo_id()


def pump(root, sec=0.5):
    end = time.time() + sec
    while time.time() < end:
        root.update()
        time.sleep(0.02)


def capture(hwnd, path):
    """PrintWindow 抓整窗（含非客户区），最接近屏幕上看到的样子。"""
    rc = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rc))
    w, h = rc.right - rc.left, rc.bottom - rc.top
    hdc_screen = user32.GetDC(0)
    hdc = gdi32.CreateCompatibleDC(hdc_screen)
    bmp = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
    gdi32.SelectObject(hdc, bmp)
    # 2 = PW_RENDERFULLCONTENT
    ok = user32.PrintWindow(hwnd, hdc, 2)
    print(f"   PrintWindow ok={ok}")
    # 取像素写 PNG
    import struct
    import zlib

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.biWidth = w
    bi.biHeight = -h          # top-down
    bi.biPlanes = 1
    bi.biBitCount = 32
    bi.biCompression = 0
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(hdc, bmp, 0, h, buf, ctypes.byref(bi), 0)

    raw = bytearray()
    data = buf.raw
    for y in range(h):
        raw.append(0)
        off = y * w * 4
        row = bytearray(w * 3)
        for x in range(w):
            b, g, r = data[off + x * 4], data[off + x * 4 + 1], data[off + x * 4 + 2]
            row[x * 3], row[x * 3 + 1], row[x * 3 + 2] = r, g, b
        raw.extend(row)

    def chunk(tag, payload):
        c = struct.pack(">I", len(payload)) + tag + payload
        return c + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 6))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as fh:
        fh.write(png)
    print(f"   saved {path}  {w}x{h}")

    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(hdc)
    user32.ReleaseDC(0, hdc_screen)


def make_window(title):
    root = tk.Tk()
    root.title(title)
    root.geometry("560x300+240+160")
    root.configure(bg="#FF00FF")            # 洋红 = 客户区底色，一眼看出缝
    tk.Frame(root, bg="#2D6FB8", height=48).pack(fill="x")
    tk.Frame(root, bg="#FF00FF").pack(fill="both", expand=True)
    pump(root, 0.6)
    return root


def main() -> int:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    # ---------- A：只去 caption
    root = make_window("A")
    hwnd = hwnd_of(root)
    st = _get(hwnd, GWL_STYLE)
    _set(hwnd, GWL_STYLE, st & ~WS_CAPTION)
    user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                        SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)
    pump(root, 0.7)
    rc = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rc))
    cr = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(cr))
    print(f"A) window={rc.right-rc.left}x{rc.bottom-rc.top} client={cr.right-client_size(cr)}x{cr.bottom} "
          if False else f"A) window={rc.right-rc.left}x{rc.bottom-rc.top} client={cr.right}x{cr.bottom}")
    print(f"   非客户区带宽 = 左右 {(rc.right-rc.left)-cr.right} 上下 {(rc.bottom-rc.top)-cr.bottom}")
    capture(hwnd, r"F:\MCLite\shots\frameA.png")
    root.destroy()

    print("done")
    return 0


def client_size(cr):
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
