"""冒烟测试打包后的 MCLite.exe：启动 → PrintWindow 截图（不受遮挡影响）→ 结束。"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

# 进程必须是 DPI aware 的：否则 GetWindowRect 拿到的是被系统缩放的逻辑坐标，
# 按它建位图会把真实的窗口右下角裁掉（125% 缩放下只剩 80% 的画面）。
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:                                         # noqa: BLE001
    try:
        user32.SetProcessDPIAware()
    except Exception:                                     # noqa: BLE001
        pass

EXE = Path(__file__).resolve().parent.parent / "dist" / "MCLite.exe"


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
        ("biPlanes", wt.WORD), ("biBitCount", wt.WORD),
        ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
        ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG),
        ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


def find_window(title_prefix: str = "MCLite") -> int | None:
    result: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def _cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        if buf.value.startswith(title_prefix):
            result.append(hwnd)
        return True

    user32.EnumWindows(_cb, 0)
    return result[0] if result else None


def capture_window(hwnd: int) -> Image.Image:
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    hdc = user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    # PW_RENDERFULLCONTENT = 0x2，能抓到 DWM 合成后的内容
    user32.PrintWindow(hwnd, mem, 2)

    bi = BITMAPINFO()
    bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.bmiHeader.biWidth = w
    bi.bmiHeader.biHeight = -h          # 负数 = 自上而下
    bi.bmiHeader.biPlanes = 1
    bi.bmiHeader.biBitCount = 32
    bi.bmiHeader.biCompression = 0
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)

    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)
    return Image.frombuffer("RGBA", (w, h), buf.raw, "raw", "BGRA", 0, 1).convert("RGB")


def kill_tree(name: str) -> None:
    """onefile 的 bootloader 会另起子进程，按名字全杀。"""
    subprocess.run(["taskkill", "/F", "/IM", f"{name}.exe"],
                   capture_output=True, check=False)


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("shots/exe.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    if not EXE.is_file():
        print("缺少", EXE)
        return 1

    proc = subprocess.Popen([str(EXE)], cwd=str(EXE.parent))
    hwnd = None
    for _ in range(60):
        time.sleep(0.5)
        hwnd = find_window()
        if hwnd:
            break
    if not hwnd:
        print("找不到窗口，进程可能崩溃")
        kill_tree(EXE.stem)
        return 2

    time.sleep(4.0)                       # 等首页异步加载
    img = capture_window(hwnd)
    img.save(out)
    print("saved ->", out, img.size)

    kill_tree(EXE.stem)
    print("exit:", proc.poll())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
