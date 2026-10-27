"""无标题栏窗口：摘掉系统的标题栏，把三个窗口按钮并进自绘顶栏。

为什么不 ``overrideredirect(True)``：那会把缩放边框、贴边吸附、任务栏缩略图、
窗口阴影、Alt+Tab 一起丢掉，还得自己实现八向缩放热区 —— 出错面远大于收益。

这里只摘掉 ``WS_CAPTION`` 一个样式位，``WS_THICKFRAME`` 留着：系统照旧负责
四周缩放、投影和 Aero Snap，只是没人再画那条标题栏，客户区于是从窗口最顶上
开始 —— 自绘顶栏和它下面就是一整块，用户反馈的「标题栏与顶栏拼接违和」消失。

拖动不再靠标题栏（已经没了），改成在顶栏空白处按下后移动时把 ``HTCAPTION``
交给系统：``WM_NCLBUTTONDOWN`` 一走，拖动、贴边吸附、拖到顶部最大化全是系统
自己的行为，我们不用复刻；因为走的是系统拖动，Tk 收不到这次拖动的
``ButtonRelease``，所以双击最大化由 TopBar 自己按「两次按下间隔 + 位移」判定。

⚠ ctypes 注意：所有 Win32 函数都必须写死 ``argtypes``/``restype``。默认
``restype`` 是 32 位 int，64 位下会把 HWND 高位截断，拿一个坏句柄去
``SetWindowLongPtr`` 会直接 access violation（0xC0000005，整个进程崩掉）。
"""

from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from ctypes import wintypes

# --- Win32 常量 ---
GWL_STYLE = -16
WS_CAPTION = 0x00C00000
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
WM_NCLBUTTONDOWN = 0x00A1
HTCAPTION = 2
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2
DWMWA_BORDER_COLOR = 34
DWMWA_CAPTION_COLOR = 35
DWMWA_TEXT_COLOR = 36

_IS64 = ctypes.sizeof(ctypes.c_void_p) == 8
_STYLE_T = ctypes.c_ssize_t if _IS64 else ctypes.c_long


def _load() -> dict:
    """一次性把要用的 Win32 入口取出来并声明签名（失败则返回空 dict）。"""
    out: dict = {}
    if sys.platform != "win32":
        return out
    try:
        u = ctypes.windll.user32
        u.GetParent.argtypes = [wintypes.HWND]
        u.GetParent.restype = wintypes.HWND
        u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        u.GetWindowRect.restype = wintypes.BOOL
        u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_uint]
        u.SetWindowPos.restype = wintypes.BOOL
        u.ReleaseCapture.argtypes = []
        u.ReleaseCapture.restype = wintypes.BOOL
        u.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                   wintypes.WPARAM, wintypes.LPARAM]
        u.SendMessageW.restype = ctypes.c_ssize_t
        if _IS64:
            u.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
            u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
            u.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
            u.SetWindowLongPtrW.restype = ctypes.c_ssize_t
            out["get"] = u.GetWindowLongPtrW
            out["set"] = u.SetWindowLongPtrW
        else:
            u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
            u.GetWindowLongW.restype = ctypes.c_long
            u.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
            u.SetWindowLongW.restype = ctypes.c_long
            out["get"] = u.GetWindowLongW
            out["set"] = u.SetWindowLongW
        out["user32"] = u
    except Exception:                                  # noqa: BLE001
        return {}
    try:
        d = ctypes.windll.dwmapi
        d.DwmSetWindowAttribute.argtypes = [wintypes.HWND, ctypes.c_uint,
                                            ctypes.c_void_p, ctypes.c_uint]
        d.DwmSetWindowAttribute.restype = ctypes.c_long
        out["dwm"] = d
    except Exception:                                  # noqa: BLE001
        out["dwm"] = None
    return out


_API = _load()


def available() -> bool:
    return bool(_API)


def hwnd_of(widget: tk.Misc) -> int:
    """Tk 的 ``winfo_id`` 拿到的是子窗口，真正的顶层窗口是它的 parent。"""
    if not _API:
        return 0
    try:
        inner = widget.winfo_id()
    except tk.TclError:
        return 0
    try:
        parent = _API["user32"].GetParent(wintypes.HWND(inner))
        return int(parent or inner)
    except Exception:                                  # noqa: BLE001
        return int(inner)


def apply(root: tk.Tk, caption_color: str = "") -> bool:
    """去掉原生标题栏。返回是否生效（非 Windows / 调用失败时 False）。

    ``caption_color`` 是顶栏最上沿的颜色：摘掉 WS_CAPTION 之后，剩下那圈
    ``WS_THICKFRAME`` 缩放边框会以 7px 非客户区露在窗口最顶上，用窗口背景色
    （#F3F3F3 灰）填 —— 蓝色顶栏上方就多了一条灰边。实测只有
    ``DWMWA_CAPTION_COLOR`` 能给它上色（``DWMWA_BORDER_COLOR`` 和窗口类背景
    画刷都改不动它），所以这里顺手把那条边染成顶栏色，看起来就是顶栏自己顶到
    了窗口边缘。不动任何窗口样式，缩放/贴边吸附/阴影/Alt+Tab 全部保留。
    """
    if not _API:
        return False
    try:
        hwnd = hwnd_of(root)
        if not hwnd:
            return False
        get, put = _API["get"], _API["set"]
        style = int(get(wintypes.HWND(hwnd), GWL_STYLE))
        if style & WS_CAPTION:
            put(wintypes.HWND(hwnd), GWL_STYLE,
                _STYLE_T(style & ~WS_CAPTION & 0xFFFFFFFF))
            _API["user32"].SetWindowPos(
                wintypes.HWND(hwnd), None, 0, 0, 0, 0,
                SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
            )
        _round_corners(hwnd)
        if caption_color:
            _paint_frame(hwnd, caption_color)
        return True
    except Exception:                                  # noqa: BLE001
        return False


def _colorref(hex_color: str) -> int:
    """``#RRGGBB`` -> Win32 COLORREF（0x00BBGGRR，注意是 BGR 顺序）。"""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return 0
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (b << 16) | (g << 8) | r


def _paint_frame(hwnd: int, hex_color: str) -> None:
    """把非客户区那条边框刷成 ``hex_color``（DWM 属性 35/36）。"""
    dwm = _API.get("dwm")
    if dwm is None:
        return
    value = wintypes.DWORD(_colorref(hex_color))
    for attr in (DWMWA_CAPTION_COLOR, DWMWA_TEXT_COLOR):
        try:
            dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd), attr,
                                      ctypes.byref(value), ctypes.sizeof(value))
        except Exception:                              # noqa: BLE001
            pass


def _round_corners(hwnd: int) -> None:
    """Win11 上让窗口保持圆角（去掉标题栏后默认仍圆，显式设一遍更稳）。"""
    dwm = _API.get("dwm")
    if dwm is None:
        return
    try:
        value = ctypes.c_int(DWMWCP_ROUND)
        dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd), DWMWA_WINDOW_CORNER_PREFERENCE,
                                  ctypes.byref(value), ctypes.sizeof(value))
    except Exception:                                  # noqa: BLE001
        pass


def begin_drag(widget: tk.Misc) -> bool:
    """让系统接管这次拖动（等价于抓住标题栏），保留贴边吸附。"""
    if not _API:
        return False
    try:
        hwnd = hwnd_of(widget)
        if not hwnd:
            return False
        _API["user32"].ReleaseCapture()
        _API["user32"].SendMessageW(wintypes.HWND(hwnd), WM_NCLBUTTONDOWN,
                                    wintypes.WPARAM(HTCAPTION), wintypes.LPARAM(0))
        return True
    except Exception:                                  # noqa: BLE001
        return False


def is_maximized(widget: tk.Misc) -> bool:
    try:
        return widget.winfo_toplevel().state() == "zoomed"
    except tk.TclError:
        return False


# 说明：v1.7.1 这里曾实现过「拉伸期间用 LockWindowUpdate + WM_SETREDRAW(0)
# 冻结整窗重绘」。它能把拖动帧从 192ms 压到 3ms，但画面会坏：Windows 会把
# 最后一帧拉伸铺满新窗口（顶栏被拉成一条长带、文字糊掉），解冻后正文还常
# 整片空白。v1.7.3 已全部拆除，改用 App._ensure_snapshot() 的像素快照方案
# （见 ui/grab.py 与 ui/app.py）。不要在这里重新加回来。


def toggle_maximize(widget: tk.Misc) -> None:
    top = widget.winfo_toplevel()
    try:
        top.state("normal" if is_maximized(top) else "zoomed")
    except tk.TclError:
        pass


def minimize(widget: tk.Misc) -> None:
    try:
        widget.winfo_toplevel().iconify()
    except tk.TclError:
        pass
