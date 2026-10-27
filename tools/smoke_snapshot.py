"""拖动/拉伸时的「像素快照」验收：画面正确性 + 每步成本。

产品行为（v1.7.3 起，见 ``App._ensure_snapshot``）：
 拖动第一帧给当前页拍一张照片盖上去 → 页面 place_forget → 之后每帧只缩放
 图片 → 停手 70ms 后摆回真页面、销毁照片。

本脚本要证的四件事：
 1. 快照真的建立了（`app._snap` 非空、页面 place_forget 了）；
 2. 拖动中截图上，页面正文**不是空白**（像素与拖动前一致）；
 3. 停手后快照销毁、页面按最终尺寸摆回（几何 + mapped）；
 4. 每步成本 ≤ 预算。

跑法：G:\\python\\python.exe -u tools\\smoke_snapshot.py
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import tkinter as tk

OK: list[str] = []
FAIL: list[str] = []

BUDGET_MS = 60.0        # 每步（改窗口+update，含系统重绘）
STOP_MS = 400.0         # 松手到页面摆回
BG_TOLERANCE = 0.004    # 与拖动前相比的最大差异像素占比

_u = ctypes.windll.user32
_u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010


def say(text: str = "") -> None:
    print(text, flush=True)


def check(cond: bool, msg: str) -> None:
    (OK if cond else FAIL).append(msg)
    say(("  ok   " if cond else "  FAIL ") + msg)


def pump(app, sec: float) -> None:
    end = time.time() + sec
    while time.time() < end:
        try:
            app.update()
        except tk.TclError:
            return
        time.sleep(0.004)


def wait_settled(app, seconds: float = 2.0) -> float:
    """泵到快照撤掉、页面摆回容器尺寸，返回耗时毫秒。"""
    from mclite.ui import frameless
    hwnd = frameless.hwnd_of(app)
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < seconds:
        try:
            app.update()
        except tk.TclError:
            break
        page = app._pages.get(app._current)
        cont = app._container
        if (app._snap is None and page is not None
                and abs(page.winfo_width() - cont.winfo_width()) <= 2):
            return (time.perf_counter() - t0) * 1000
        time.sleep(0.004)
    _ = hwnd
    return (time.perf_counter() - t0) * 1000


def capture(page, size: tuple[int, int] | None = None):
    """抓页面上的一块。默认抓整页，但拖动中窗口可能已经比页面小，
    必须显式限制尺寸，否则会抓到窗口外面的桌面。"""
    from probe_fl_screen import grab_screen
    x, y = page.winfo_rootx(), page.winfo_rooty()
    if size is None:
        return grab_screen(x, y, page.winfo_width(), page.winfo_height())
    return grab_screen(x, y, size[0], size[1])


def diff_ratio(a, b) -> float:
    """两张 PIL 图里明显不同的像素占比（忽略 6/255 的色彩抖动）。"""
    if a.size != b.size:
        return 1.0
    pa, pb = a.convert("RGB"), b.convert("RGB")
    total = a.size[0] * a.size[1]
    if total <= 0:
        return 1.0
    d = 0
    da, db = pa.tobytes(), pb.tobytes()
    for i in range(0, len(da), 3):
        if (abs(da[i] - db[i]) > 6 or abs(da[i + 1] - db[i + 1]) > 6
                or abs(da[i + 2] - db[i + 2]) > 6):
            d += 1
    return d / total


def run(page_name: str) -> int:
    from mclite.ui import frameless, theme
    from mclite.ui.app import App

    OK.clear()
    FAIL.clear()
    say(f"== {page_name} ==")

    app = App()
    app.create_pages()
    app.show_page(page_name)
    pump(app, 1.6)
    app.geometry("1160x724+120+90")
    pump(app, 0.8)
    app.deiconify()
    app.lift()
    app.attributes("-topmost", True)
    app.focus_force()
    pump(app, 0.6)

    page = app._pages[page_name]
    hwnd = frameless.hwnd_of(app)
    cont = app._container
    # 比对区域取「拖到最小也仍然在窗口里」的左上角一块：拖动中窗口最小
    # 820x520 → 容器 587x472，所以 560x396 是安全的。坐标用容器的，因为拖动
    # 期间页面被 place_forget 了，页面自己的 rootx 不可靠。
    BOX = (cont.winfo_rootx(), cont.winfo_rooty(), 560, 396)
    ref = capture(cont, (BOX[2], BOX[3]))

    # 拖大 → 拖小共 18 步
    costs: list[float] = []
    mid_img = None
    snap_seen = 0
    for i in range(1, 19):
        f = i / 18.0
        w = int(1160 + (820 - 1160) * f)
        h = int(724 + (520 - 724) * f)
        t = time.perf_counter()
        _u.SetWindowPos(wintypes.HWND(hwnd), None, 120, 90, w, h,
                        SWP_NOZORDER | SWP_NOACTIVATE)
        try:
            app.update()
        except tk.TclError:
            break
        costs.append((time.perf_counter() - t) * 1000)
        if app._snap is not None:
            snap_seen += 1
        if i == 9:
            mid_img = capture(cont, (BOX[2], BOX[3]))
        time.sleep(0.014)

    check(snap_seen > 0, f"拖动中建立了快照（{snap_seen}/18 帧有快照）")
    costs.sort()
    mid = costs[len(costs) // 2]
    check(mid <= BUDGET_MS, f"每步中位 {mid:.1f} ms ≤ {BUDGET_MS:.0f}")

    if mid_img is not None and mid_img.size == ref.size:
        ratio = diff_ratio(ref, mid_img)
        check(ratio <= BG_TOLERANCE,
              f"拖动中画面与拖动前一致（差异 {ratio*100:.2f}% ≤ {BG_TOLERANCE*100:.1f}%）")
        mid_img.save(str(ROOT / "shots" / f"snap_{page_name}_mid.png"))
        ref.save(str(ROOT / "shots" / f"snap_{page_name}_ref.png"))
    else:
        check(False, f"拖动中截图尺寸与拖动前不同（{mid_img.size if mid_img else None}"
                     f" vs {ref.size}），无法比对")

    stopped = wait_settled(app)
    check(stopped <= STOP_MS, f"松手后 {stopped:.0f} ms 内摆回 ≤ {STOP_MS:.0f}")
    check(app._snap is None, "松手后快照已销毁")

    cw, ch = app._container.winfo_width(), app._container.winfo_height()
    pw, ph = page.winfo_width(), page.winfo_height()
    check(abs(pw - cw) <= 2 and abs(ph - ch) <= 2,
          f"页面尺寸跟上了容器（页面 {pw}x{ph} / 容器 {cw}x{ch}）")
    check(page.winfo_ismapped() == 1, "页面重新可见")

    from probe_fl_screen import grab_screen
    grab_screen(0, 0, 1500, 850).save(str(ROOT / "shots" / f"snap_{page_name}_after.png"))

    # 再来一轮：确认快照机制可以重复使用（第二次不能因为 _snap_ok 被关掉）
    before = app._snap_ok
    for i in range(1, 7):
        w = int(820 + (1000 - 820) * (i / 6))
        _u.SetWindowPos(wintypes.HWND(hwnd), None, 120, 90, w, 600,
                        SWP_NOZORDER | SWP_NOACTIVATE)
        try:
            app.update()
        except tk.TclError:
            break
        time.sleep(0.014)
    stopped2 = wait_settled(app)
    check(app._snap_ok == before, "_snap_ok 未被误关（第二轮仍可用）")
    check(stopped2 <= STOP_MS, f"第二轮松手 {stopped2:.0f} ms 摆回 ≤ {STOP_MS:.0f}")

    # 第三轮：**变大**。快照贴在左上角、不缩放，所以新露出的右侧区域应该是
    # 容器底色 —— 绝不能是被拉伸的内容（用户截图里那坨拉伸的蓝色就是这个）。
    from mclite.ui.theme import BG as BG_COLOR
    bg_rgb = tuple(int(BG_COLOR[i:i + 2], 16) for i in (1, 3, 5))
    # 先把窗口缩到 900x560，让快照拍一张小的
    for i in range(1, 5):
        _u.SetWindowPos(wintypes.HWND(hwnd), None, 120, 90, 900, 560,
                        SWP_NOZORDER | SWP_NOACTIVATE)
        try:
            app.update()
        except tk.TclError:
            break
        time.sleep(0.014)
    wait_settled(app)
    # 再拖大，中途抓图
    grown = None
    snap_w = 0
    for i in range(1, 9):
        w = int(900 + (1280 - 900) * (i / 8))
        h = int(560 + (760 - 560) * (i / 8))
        _u.SetWindowPos(wintypes.HWND(hwnd), None, 120, 90, w, h,
                        SWP_NOZORDER | SWP_NOACTIVATE)
        try:
            app.update()
        except tk.TclError:
            break
        if i == 8 and app._snap is not None:
            cv = app._snap[0]
            snap_w = cv.winfo_width()
            cw = app._container.winfo_width()
            ch = app._container.winfo_height()
            # 只抓容器自己的范围：容器比窗口小（左边有 232px 侧栏），多抓就
            # 抓到窗口外面的桌面上了。
            grown = capture(app._container, (cw, ch))
        time.sleep(0.014)

    if grown is not None and snap_w > 0 and grown.size[0] > snap_w + 40:
        # 快照宽度之外、但仍在容器内的这一条 = 窗口变大新露出的区域
        px = grown.convert("RGB")
        hits = total = 0
        for gx in range(snap_w + 20, px.size[0]):
            for gy in range(80, min(px.size[1] - 80, 600), 4):
                r, g, b = px.getpixel((gx, gy))
                total += 1
                if (abs(r - bg_rgb[0]) <= 12 and abs(g - bg_rgb[1]) <= 12
                        and abs(b - bg_rgb[2]) <= 12):
                    hits += 1
        frac = hits / total if total else 1.0
        check(frac >= 0.85,
              f"变大时新露出的是容器底色而非拉伸内容（{frac*100:.0f}% ≥ 85%）")
        grown.save(str(ROOT / "shots" / f"snap_{page_name}_grow.png"))
    else:
        check(False, f"没抓到变大中的画面（image={grown is not None} "
                     f"snap_w={snap_w}）")
    wait_settled(app)

    try:
        app.attributes("-topmost", False)
        app.destroy()
    except tk.TclError:
        pass
    return 0


def main() -> int:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:                            # noqa: BLE001
        pass
    import mclite.ui.theme as theme
    theme.set_theme("pcl")

    if len(sys.argv) > 1:
        run(sys.argv[1])
        say(f"PASS {len(OK)} / FAIL {len(FAIL)}")
        if FAIL:
            for f in FAIL:
                say("  ! " + f)
            return 1
        say("ALL PASS")
        return 0

    # 每页必须独立进程：同进程建第二个 App() 会撞
    # "can't invoke image command: application has been destroyed"（hero canvas）。
    import subprocess
    rc = 0
    for name in ("home", "install", "settings"):
        proc = subprocess.run([sys.executable, "-u", str(Path(__file__).resolve()),
                               name], cwd=str(ROOT))
        if proc.returncode != 0:
            rc = 1
        say()
    say("ALL PAGES PASS" if rc == 0 else "SOME PAGES FAILED")
    return rc


if __name__ == "__main__":
    sys.exit(main())
