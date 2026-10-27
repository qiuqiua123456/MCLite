"""快照抓图的三条路，比谁快、谁不含别的窗口。

屏幕 DC 的 BitBlt 会被挡在前面的窗口污染；PrintWindow 只渲染窗口自己。
PIL 的 ImageTk 直接贴，省掉 PNG 编码。

跑法：G:\\python\\python.exe tools\\probe_capture.py
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tkinter as tk

from mclite.ui import theme
from mclite.ui.app import App
from probe_fl_screen import grab_screen

u = ctypes.windll.user32
g = ctypes.windll.gdi32
u.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
u.PrintWindow.restype = wintypes.BOOL
g.CreateCompatibleDC.argtypes = [wintypes.HDC]
g.CreateCompatibleDC.restype = wintypes.HDC
g.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
g.CreateCompatibleBitmap.restype = wintypes.HBITMAP
g.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]


def pump(app, sec: float) -> None:
    end = time.time() + sec
    while time.time() < end:
        try:
            app.update()
        except tk.TclError:
            return
        time.sleep(0.004)


def print_window(hwnd: int, x: int, y: int, w: int, h: int):
    """用 PrintWindow 渲染窗口自己的内容（不含遮挡它的别的窗口）。"""
    from PIL import Image
    screen = u.GetDC(None)
    mem = g.CreateCompatibleDC(screen)
    bmp = g.CreateCompatibleBitmap(screen, w, h)
    g.SelectObject(mem, bmp)
    ok = u.PrintWindow(wintypes.HWND(hwnd), mem, 2)      # PW_RENDERFULLCONTENT
    if not ok:
        ok = u.PrintWindow(wintypes.HWND(hwnd), mem, 0)
    # 从整窗位图里裁页面区域：client 原点相对窗口的偏移由调用方给
    from probe_fl_screen import BITMAPINFO, BITMAPINFOHEADER
    bi = BITMAPINFO()
    bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.bmiHeader.biWidth = w
    bi.bmiHeader.biHeight = -h
    bi.bmiHeader.biPlanes = 1
    bi.bmiHeader.biBitCount = 32
    bi.bmiHeader.biCompression = 0
    buf = ctypes.create_string_buffer(w * h * 4)
    g.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)
    g.DeleteObject(bmp)
    g.DeleteDC(mem)
    u.ReleaseDC(None, screen)
    return Image.frombuffer("RGBA", (w, h), buf.raw, "raw", "BGRA", 0, 1).convert("RGB")


def main() -> int:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:                              # noqa: BLE001
        pass
    from PIL import ImageTk

    theme.set_theme("pcl")
    app = App()
    app.create_pages()
    app.show_page("home")
    pump(app, 1.8)
    app.geometry("1160x724+120+90")
    pump(app, 1.4)
    app.deiconify()
    app.lift()
    app.attributes("-topmost", True)
    app.focus_force()
    pump(app, 0.5)

    page = app._pages.get(app._current)
    app.update()
    px, py = page.winfo_rootx(), page.winfo_rooty()
    pw, ph = page.winfo_width(), page.winfo_height()
    print(f"page {pw}x{ph} @ {px},{py}")

    # A: 屏幕 DC + PNG 编码（现在探针用的）
    t = time.perf_counter()
    img = grab_screen(px, py, pw, ph)
    t1 = time.perf_counter()
    import base64
    import io
    bufio = io.BytesIO()
    img.save(bufio, format="PNG")
    data = base64.b64encode(bufio.getvalue()).decode("ascii")
    ph_a = tk.PhotoImage(master=app, data=data, format="png")
    t2 = time.perf_counter()
    print(f"A 屏幕+PNG  抓 {(t1-t)*1000:5.1f} 编码+建图 {(t2-t1)*1000:5.1f} "
          f"合计 {(t2-t)*1000:5.1f} ms")

    # B: 屏幕 DC + ImageTk（无编码）
    t = time.perf_counter()
    img = grab_screen(px, py, pw, ph)
    t1 = time.perf_counter()
    ph_b = ImageTk.PhotoImage(img, master=app)
    t2 = time.perf_counter()
    print(f"B 屏幕+Tk   抓 {(t1-t)*1000:5.1f} 建图      {(t2-t1)*1000:5.1f} "
          f"合计 {(t2-t)*1000:5.1f} ms")

    # C: PrintWindow + ImageTk
    from ctypes import wintypes as wt
    hwnd = u.GetParent(app.winfo_id())
    r = wt.RECT()
    u.GetWindowRect(wt.HWND(hwnd), ctypes.byref(r))
    cx, cy = px - r.left, py - r.top
    t = time.perf_counter()
    ww, wh = r.right - r.left, r.bottom - r.top
    full = print_window(hwnd, 0, 0, ww, wh)
    t1 = time.perf_counter()
    crop = full.crop((cx, cy, cx + pw, cy + ph))
    ph_c = ImageTk.PhotoImage(crop, master=app)
    t2 = time.perf_counter()
    print(f"C 打印+Tk   渲染 {(t1-t)*1000:5.1f} 裁剪+建图 {(t2-t1)*1000:5.1f} "
          f"合计 {(t2-t)*1000:5.1f} ms")
    crop.save("shots/cap_printwindow.png")
    img.save("shots/cap_screen.png")

    try:
        app.attributes("-topmost", False)
        app.destroy()
    except tk.TclError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
