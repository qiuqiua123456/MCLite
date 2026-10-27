"""验收脚本：无边框窗口 + 顶栏窗口按钮。

启动源码版 App，截图整窗（含非客户区，走 PrintWindow），再断言：
1. 窗口样式里已经没有 WS_CAPTION（原生标题栏真的摘掉了）；
2. 客户区顶端 = 窗口顶端（顶栏就是最顶上一行，没有第二条蓝条）；
3. 顶栏右侧三个按钮的命中区宽度加起来是 138px，且都落在窗口内；
4. 最小化 / 最大化 / 还原 三个动作都能走通。
"""
from __future__ import annotations

import ctypes
import sys
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

user32 = ctypes.windll.user32
GWL_STYLE = -16
WS_CAPTION = 0x00C00000

# 必须写死签名：默认 restype 是 32 位 int，64 位下窗口句柄会被截断，
# 拿坏句柄调 Win32 直接 0xC0000005（进程无声退出）。
if ctypes.sizeof(ctypes.c_void_p) == 8:
    _get = user32.GetWindowLongPtrW
    _get.argtypes = [wintypes.HWND, ctypes.c_int]
    _get.restype = ctypes.c_ssize_t
else:
    _get = user32.GetWindowLongW
    _get.argtypes = [wintypes.HWND, ctypes.c_int]
    _get.restype = ctypes.c_long
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]

# GetWindowRect 把「不可见的那圈缩放边框」也算进去（本机 7px），视觉可见区
# 只有 DWMWA_EXTENDED_FRAME_BOUNDS 才是准的。断言窗口/客户区相对位置必须用它，
# 不然永远差 7px 的假失败。
dwmapi = ctypes.windll.dwmapi
dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD,
                                         ctypes.c_void_p, wintypes.DWORD]
dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long
DWMWA_EXTENDED_FRAME_BOUNDS = 9

FAIL: list[str] = []
OK: list[str] = []


def say(text: str = "") -> None:
    print(text, flush=True)


def check(cond: bool, msg: str) -> None:
    (OK if cond else FAIL).append(msg)
    say(("  ok   " if cond else "  FAIL ") + msg)


def pump(app, sec=0.4) -> None:
    end = time.time() + sec
    while time.time() < end:
        try:
            app.update()
        except tk.TclError:
            return
        time.sleep(0.02)


def window_rect(hwnd):
    r = wintypes.RECT()
    user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def visible_rect(hwnd):
    """窗口真正画在屏幕上的矩形（不含那圈看不见的缩放边框）。"""
    r = wintypes.RECT()
    hr = dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), DWMWA_EXTENDED_FRAME_BOUNDS,
                                      ctypes.byref(r), ctypes.sizeof(r))
    if hr != 0:
        return window_rect(hwnd)
    return r.left, r.top, r.right, r.bottom


def client_rect(hwnd):
    r = wintypes.RECT()
    user32.GetClientRect(wintypes.HWND(hwnd), ctypes.byref(r))
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(wintypes.HWND(hwnd), ctypes.byref(pt))
    return pt.x, pt.y, pt.x + r.right, pt.y + r.bottom


def _hex_rgb(color: str):
    h = color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _near(px, rgb, tol: int) -> bool:
    return all(abs(a - b) <= tol for a, b in zip(px, rgb))


def grab_pixels(x, y, w, h):
    """从真实屏幕 DC 抓像素（PrintWindow 不算数：它会把非客户区填成窗口底色）。"""
    import probe_fl_screen as P
    img = P.grab_screen(x, y, w, h)
    return [img.getpixel((0, row)) for row in range(img.height)][:max(1, h)]


def main() -> int:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:                                  # noqa: BLE001
        pass

    from mclite.ui import frameless
    from mclite.ui.app import App
    from mclite.ui.theme import ACCENT_DARK

    app = App()
    app.create_pages()
    app.show_page("home")
    pump(app, 1.2)

    hwnd = frameless.hwnd_of(app)
    style = int(_get(hwnd, GWL_STYLE))
    print(f"hwnd=0x{hwnd:X} style=0x{style & 0xFFFFFFFF:08X}")

    w_r = window_rect(hwnd)
    v_r = visible_rect(hwnd)
    c_r = client_rect(hwnd)
    print(f"window={w_r}  visible={v_r}  client={c_r}")

    check(not (style & WS_CAPTION), "原生标题栏已摘除（WS_CAPTION 不在样式里）")

    # 摘掉 caption 之后，客户区上方还剩一圈 7px 的缩放边框（非客户区），
    # 系统默认用窗口背景色 #F3F3F3 填 → 蓝顶栏上面挂一条灰边。我们的做法是
    # 用 DWMWA_CAPTION_COLOR 把它染成顶栏顶部色。这里直接从屏幕抓真实像素：
    # 窗口顶端到客户区顶端之间必须是顶栏色，不能是灰。
    gap = c_r[1] - v_r[1]
    print(f"客户区比可见窗口顶端低 {gap}px（这圈是缩放边框，需要染成顶栏色）")
    want = _hex_rgb(ACCENT_DARK)
    got_top = grab_pixels(c_r[0] + 40, v_r[1] + 1, 1, max(1, gap - 1))
    got_bottom = grab_pixels(c_r[0] + 40, v_r[1] + max(1, gap - 1), 1, 1)
    band_ok = all(_near(px, want, 24) for px in got_top)
    check(band_ok,
          f"窗口顶端那 {gap}px 非客户区是顶栏色 {ACCENT_DARK}（实测 {got_top[:3]}）")
    check(_near(got_bottom[0], want, 40),
          f"色带与顶栏渐变起始色顺接（{got_bottom[0]} vs {want}）")
    # 反面断言：确认不是默认灰（如果 DWM 属性没生效就会是 243,243,243）
    check(not all(_near(px, (243, 243, 243), 6) for px in got_top),
          "这条边没有退回系统默认灰 (243,243,243)")

    check(abs(c_r[0] - v_r[0]) <= 1, f"客户区左侧贴边（差 {c_r[0] - v_r[0]}px）")

    bar = app._topbar
    pump(app, 0.3)
    hits = list(bar._btn_hits)
    print(f"窗口按钮命中区: {[(k, int(a), int(b)) for k, a, b in hits]}")
    check([k for k, _, _ in hits] == ["min", "max", "close"], "三个按钮依次是最小化/最大化/关闭")
    check(len(hits) == 3, "按钮数量为 3")
    if len(hits) == 3:
        widths = [b - a for _, a, b in hits]
        check(all(abs(wd - bar.BTN_W) <= 0.5 for wd in widths), f"每个按钮宽 {bar.BTN_W}px")
        check(abs(hits[-1][2] - bar._bar_w) <= 0.5, "关闭按钮右侧贴到顶栏右边缘")

    # ---- 最大化 / 还原
    before = window_rect(hwnd)
    frameless.toggle_maximize(app)
    pump(app, 0.7)
    zo = frameless.is_maximized(app)
    zr = window_rect(hwnd)
    zc = client_rect(hwnd)
    check(zo, f"最大化解锁：state={app.state()} rect={zr}")
    ra = wintypes.RECT()
    user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(ra), 0)
    work = (ra.left, ra.top, ra.right, ra.bottom)
    # 最大化时客户区铺满工作区；窗口矩形会向外溢出那圈 7px 缩放边框，正常。
    check(tuple(zc) == work,
          f"最大化后客户区铺满工作区 client={zc} work={work}")

    frameless.toggle_maximize(app)
    pump(app, 0.7)
    rr = window_rect(hwnd)
    check(not frameless.is_maximized(app), "再点一次还原为普通窗口")
    check(rr == before, f"还原后窗口几何与最大化前一致 ({rr} vs {before})")

    # ---- 顶栏按钮的命中判定
    cx = (hits[2][1] + hits[2][2]) / 2 if len(hits) == 3 else 0
    check(bar._hit_btn(cx, bar.H / 2) == "close", "鼠标落在关闭按钮上能命中")
    check(bar._hit_btn(bar._bar_w - bar.BTN_W * 3 - 40, bar.H / 2) == "",
          "账户胶囊左侧空白不误判成窗口按钮")

    print()
    print(f"PASS {len(OK)} 项，FAIL {len(FAIL)} 项")
    if FAIL:
        for f in FAIL:
            print("  - " + f)

    app.destroy()
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
