"""geometry() 本身要多久？拖动卡顿的嫌疑句。

前一个 probe 的时间测量把 `app.geometry(...)` 排除在外，而它在 Windows 上是
同步 SetWindowPos —— 会立刻触发整窗重绘。如果这一句就要 70ms，那「每帧 10ms
的绘制」根本不是主要成本，减控件才是唯一出路。

对照：空窗口 vs 我们的 app（含整棵控件树）。
"""
from __future__ import annotations

import statistics
import sys
import time
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

WIDTHS = (1128, 1132, 1136, 1140, 1144, 1148, 1152, 1156, 1160, 1164)


def drain(root, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        root.update()
        time.sleep(0.005)


def cost_geometry(root) -> tuple[float, float]:
    geom, idle = [], []
    for w in WIDTHS * 3:
        t0 = time.perf_counter()
        root.geometry(f"{w}x724")
        geom.append((time.perf_counter() - t0) * 1000.0)
        t1 = time.perf_counter()
        root.update_idletasks()
        idle.append((time.perf_counter() - t1) * 1000.0)
        root.update()
    return statistics.median(geom), statistics.median(idle)


def main() -> int:
    # --- 空窗口
    root = tk.Tk()
    root.geometry("1160x724")
    cv = tk.Canvas(root, bg="#0E5FB8", highlightthickness=0)
    cv.pack(fill="both", expand=True)
    drain(root, 0.6)
    g, i = cost_geometry(root)
    print(f"空窗口                geometry() 中位 {g:6.2f} | update_idletasks {i:5.2f} ms")
    root.destroy()

    # --- 真实 app
    from mclite.ui import app as app_mod

    app = app_mod.App()
    app.create_pages()
    drain(app, 1.0)
    app.show_page("home")
    drain(app, 0.8)
    g, i = cost_geometry(app)
    print(f"app home 页           geometry() 中位 {g:6.2f} | update_idletasks {i:5.2f} ms")

    # 顶栏不重画
    bar = app._topbar
    real = bar._draw
    bar._draw = lambda *a, **k: None
    drain(app, 0.3)
    g, i = cost_geometry(app)
    print(f"app 顶栏不重画         geometry() 中位 {g:6.2f} | update_idletasks {i:5.2f} ms")
    bar._draw = real

    # 页面内容全 unmapped
    page = app._pages["home"]
    hidden = []
    for w in list(page.winfo_children()):
        try:
            if w.winfo_manager() == "pack":
                w.pack_forget()
                hidden.append(w)
        except Exception:                      # noqa: BLE001
            pass
    drain(app, 0.3)
    g, i = cost_geometry(app)
    print(f"app 页面内容 unmapped  geometry() 中位 {g:6.2f} | update_idletasks {i:5.2f} ms"
          f"  (隐藏 {len(hidden)} 块)")

    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
