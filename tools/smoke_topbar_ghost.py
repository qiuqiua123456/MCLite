"""顶栏残影回归：窗口改尺寸时画布 item 不能越攒越多。

用户报的「拖动时候出现bug / 拖动出现残影」有两个来源：

1. ``TopBar._draw()`` 在宽度变化时只删了渐变（tag ``topbg``/``topline``），
   前景（品牌、三个导航胶囊、账户胶囊、三个窗口按钮）没删，新前景又叠一层。
   每改一次宽度多 14 个 item，实测 8 档之后同一串文字在画布上叠了 6 份，
   那些旧 item 落在窗口新露出的区域里就是错位重影。
2. 冻结（``LockWindowUpdate`` + ``WM_SETREDRAW(0)``）期间窗口改了位置，
   ``thaw()`` 的 ``RedrawWindow`` 只覆盖当前矩形，旧位置定格的像素没人擦。

本脚本只查第 1 条能做到确定性的部分，加上冻结路径结束后 item 数不涨；
第 2 条靠截图肉眼验收（``shot_ghost.py``），因为屏幕像素受壁纸/别的窗口干扰。

跑法：G:\\python\\python.exe tools\\smoke_topbar_ghost.py
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk

from mclite.ui import theme
from mclite.ui.app import App

BASE_ITEMS = 175         # 1162 宽时顶栏 canvas 的 item 数（背景 160 + 底线 + 8 文字 + 前景）
BASE_TEXTS = {"M", "MCLite", "开始", "下载", "设置", "Steve", "\u25be", "\u2715"}
WIDTHS = (1120, 1140, 1160, 1180, 1160, 1240, 1300, 1160)

FAIL: list[str] = []
OK: list[str] = []


def check(cond: bool, msg: str) -> None:
    (OK if cond else FAIL).append(msg)
    print(("  ok   " if cond else "  FAIL ") + msg, flush=True)


def pump(app, sec: float = 0.3) -> None:
    end = time.time() + sec
    while time.time() < end:
        try:
            app.update()
        except tk.TclError:
            return
        time.sleep(0.01)


def texts_of(bar) -> list[str]:
    out = []
    for item in bar.find_all():
        if bar.type(item) == "text":
            try:
                out.append(bar.itemcget(item, "text"))
            except tk.TclError:
                pass
    return out


def snap(bar) -> tuple[int, int, set[str]]:
    ts = texts_of(bar)
    return len(bar.find_all()), len(ts), set(ts)


def main() -> int:
    theme.set_theme("pcl")
    app = App()
    app.create_pages()
    pump(app, 1.0)
    app.show_page("home")
    pump(app, 0.8)
    app.geometry("1162x724")
    pump(app, 0.6)

    bar = app._topbar
    n0, t0, set0 = snap(bar)
    print(f"\n[基线] 顶栏 {bar.winfo_width()}x{bar.H}  item {n0}  文字 {t0} 个", flush=True)
    check(set0 == BASE_TEXTS, f"基线文字集合 = {sorted(BASE_TEXTS)}（实际 {sorted(set0)}）")
    check(n0 == BASE_ITEMS, f"基线 item 数 = {BASE_ITEMS}（实际 {n0}）")

    # ---------- 用例 1：连续改宽度，item 不累积 ----------
    print("\n[用例 1] 连续改 8 档宽度", flush=True)
    counts, texts = [], []
    for w in WIDTHS:
        app.geometry(f"{w}x724")
        pump(app, 0.35)
        n, t, s = snap(bar)
        counts.append(n)
        texts.append(t)
        print(f"  width {w:4d} → item {n:3d}  文字 {t:2d} 个", flush=True)
    check(all(c == BASE_ITEMS for c in counts),
          f"每档 item 数恒为 {BASE_ITEMS}（实际 {counts}）")
    check(all(t == len(BASE_TEXTS) for t in texts),
          f"每档文字项恒为 {len(BASE_TEXTS)} 个（实际 {texts}）")
    check(set(texts_of(bar)) == BASE_TEXTS,
          f"8 档后文字集合不变（实际 {sorted(set(texts_of(bar)))}）")

    # ---------- 用例 2：快照路径（模拟拖动）结束后 item 不涨 ----------
    # v1.7.3 起拉伸不再用 frameless.freeze/thaw（会让画面被拉伸、正文空白），
    # 改成 App._ensure_snapshot()：拖动第一帧拍照片盖住页面。这里手动驱动一遍
    # 同一条路径，确认顶栏 item 不会因为反复摆页面而累积。
    print("\n[用例 2] 快照路径：拍快照 → 连续改宽 → 摆回页面 → 顶栏补画", flush=True)

    app.geometry("1162x724")
    pump(app, 0.4)
    before = len(bar.find_all())
    app._ensure_snapshot()
    check(app._snap is not None, "拖动开始时建立了快照")
    page = app._pages.get(app._current)
    check(page is not None and not page.winfo_manager(),
          "快照期间真页面已 place_forget")
    for w in (1120, 1140, 1160, 1180):
        app.geometry(f"{w}x724")
        pump(app, 0.12)
    during = len(bar.find_all())
    # 现在顶栏是正常重画的（不再冻结），所以 item 数应该每档都稳定在 BASE_ITEMS
    check(during == BASE_ITEMS,
          f"拖宽 4 档后顶栏 item 仍是 {BASE_ITEMS}（实际 {during}）")
    app._flush_page_size()
    pump(app, 0.4)
    bar._sync_size_and_draw()
    pump(app, 0.3)
    after = len(bar.find_all())
    check(app._snap is None, "停手后快照已销毁")
    check(after == BASE_ITEMS, f"摆回页面并补画后 item 仍是 {BASE_ITEMS}（实际 {after}）")
    check(set(texts_of(bar)) == BASE_TEXTS,
          f"摆回后文字集合不变（实际 {sorted(set(texts_of(bar)))}）")
    check(bar._bar_w == bar.winfo_width(),
          f"补画时按真实宽度同步 _bar_w（{bar._bar_w} vs {bar.winfo_width()}）")

    # ---------- 用例 3：hover 反复重画也不涨 ----------
    print("\n[用例 3] 悬停/离开顶栏 12 次", flush=True)
    app.geometry("1162x724")
    pump(app, 0.4)
    for i in range(12):
        bar._set_hover(("home", "launch", "")[i % 3])
        bar._btn_hover = ("min", "max", "close")[i % 3]
        bar._draw()
        pump(app, 0.03)
    bar._set_hover("")
    bar._btn_hover = ""
    bar._draw()
    pump(app, 0.2)
    n3, t3, s3 = snap(bar)
    check(n3 == BASE_ITEMS, f"hover 12 次后 item 数仍 {BASE_ITEMS}（实际 {n3}）")
    check(s3 == BASE_TEXTS, f"hover 12 次后文字集合不变（实际 {sorted(s3)}）")

    try:
        app.destroy()
    except tk.TclError:
        pass

    print(f"\nPASS {len(OK)} / FAIL {len(FAIL)}", flush=True)
    if FAIL:
        for m in FAIL:
            print("  ! " + m, flush=True)
        return 1
    print("ALL PASS", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
