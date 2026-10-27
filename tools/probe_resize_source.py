"""决定性实验：页面已用绝对尺寸放置时，窗口 resize 一帧的布局成本来自哪里。

对比五种状态下 resize 一次的布局耗时（update_idletasks，不含绘制）：
  1. 现状（页面绝对尺寸 place 着）
  2. 页面全部 place_forget（外壳+顶栏仍在）
  3. 页面 place_forget + 顶栏 place_forget
  4. 只留一个空 Frame
  5. 页面恢复，但把顶栏换成普通 Frame
"""
from __future__ import annotations

import statistics
import sys
import time
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def pump(app, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        try:
            app.update_idletasks()
            app.update()
        except Exception:                      # noqa: BLE001
            return
        time.sleep(0.005)


def resize_cost(app, widths=(1000, 1240, 1080, 1400, 1160)) -> tuple[float, float]:
    samples = []
    for w in widths:
        app.geometry(f"{w}x724")
        t0 = time.perf_counter()
        app.update_idletasks()
        samples.append((time.perf_counter() - t0) * 1000.0)
        time.sleep(0.01)
    return statistics.median(samples), max(samples)


def main() -> int:
    from mclite.ui.app import App

    app = App()
    app.create_pages()
    pump(app, 0.8)
    app.show_page("home")
    pump(app, 0.5)

    mid, worst = resize_cost(app)
    print(f"1 现状（home 页面 place 着）        中位 {mid:6.1f} 最慢 {worst:6.1f} ms")

    pages = [p for p in app._pages.values()]
    for p in pages:
        p.place_forget()
    pump(app, 0.4)
    mid, worst = resize_cost(app)
    print(f"2 页面全部 place_forget            中位 {mid:6.1f} 最慢 {worst:6.1f} ms")

    app._topbar.pack_forget()
    pump(app, 0.3)
    mid, worst = resize_cost(app)
    print(f"3 再加顶栏 pack_forget             中位 {mid:6.1f} 最慢 {worst:6.1f} ms")

    app._side.pack_forget()
    pump(app, 0.3)
    mid, worst = resize_cost(app)
    print(f"4 再加左侧栏 pack_forget           中位 {mid:6.1f} 最慢 {worst:6.1f} ms")

    for p in pages:
        p.pack_forget()
    pump(app, 0.3)
    mid, worst = resize_cost(app)
    print(f"5 只剩空容器                       中位 {mid:6.1f} 最慢 {worst:6.1f} ms")

    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
