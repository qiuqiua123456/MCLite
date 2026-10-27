"""接着 probe_jank.py，确认 82ms 里到底是什么在花时间。

对照：把「页面容器里放什么」换掉，其他一切不变。
  1 现状（整页内容）
  2 空 Frame 当作页面（同样尺寸、同样 place 方式）
  3 整页内容，但页面缩到 120x120（画得少）
  4 整页内容，但页面的子孙控件全部 unmapped（place_forget 内部的 scroller）
"""
from __future__ import annotations

import statistics
import sys
import time
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

STEP_MS = 16
FRAME_BUDGET = 16.6


def drain(app, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.update()
        time.sleep(0.005)


def heartbeat_drag(app, start=1120, end=1300, step=4) -> dict:
    app.geometry(f"{start}x724")
    drain(app, 0.35)
    widths = list(range(start, end + 1, step))
    lateness: list[float] = []
    it = {"i": 0, "last": time.perf_counter()}

    def beat():
        now = time.perf_counter()
        lateness.append(max(0.0, (now - it["last"]) * 1000.0 - STEP_MS))
        it["last"] = now
        i = it["i"]
        if i < len(widths):
            it["i"] = i + 1
            app.geometry(f"{widths[i]}x724")
            app.after(STEP_MS, beat)

    app.after(STEP_MS, beat)
    deadline = time.perf_counter() + 30
    while it["i"] < len(widths) and time.perf_counter() < deadline:
        app.update()
        time.sleep(0.003)
    drain(app, 0.6)
    n = len(lateness)
    return {"mid": statistics.median(lateness), "p90": sorted(lateness)[int(n * 0.9)],
            "worst": max(lateness), "n": n,
            "over": sum(1 for v in lateness if v > FRAME_BUDGET)}


def show(tag: str, r: dict) -> None:
    print(f"  {tag:26s} 中位 {r['mid']:6.1f} p90 {r['p90']:6.1f} 最差 {r['worst']:7.1f} ms"
          f" | 掉帧 {r['over']:2d}/{r['n']}")


def main() -> int:
    from mclite.ui import app as app_mod

    app = app_mod.App()
    app.create_pages()
    drain(app, 0.8)
    app.show_page("home")
    drain(app, 0.6)
    page = app._pages["home"]
    cont = app._container

    print("\n--- 换掉容器里放的东西，量 16ms 拖动的心跳延迟")
    show("1 现状（整页）", heartbeat_drag(app))

    page.place_forget()
    empty = tk.Frame(cont, bg="#202020")
    app._place_page(empty, cont.winfo_width(), cont.winfo_height())
    drain(app, 0.3)
    show("2 空 Frame 当页面", heartbeat_drag(app))

    empty.place_forget()
    app._place_page(page, cont.winfo_width(), cont.winfo_height())
    drain(app, 0.3)
    show("3 整页但缩到 120x120", heartbeat_drag(app))  # 尺寸由 _flush 覆盖，这里只测一次

    # 4：把页面里真正占面积的滚动区 unmapped
    page.place_forget()
    empty.place_forget()
    hidden = []
    for w in page.winfo_children():
        try:
            if w.winfo_manager():
                w.pack_forget() if w.winfo_manager() == "pack" else w.grid_forget()
                hidden.append(w)
        except Exception:                      # noqa: BLE001
            pass
    app._place_page(page, cont.winfo_width(), cont.winfo_height())
    drain(app, 0.3)
    show(f"4 页面里 {len(hidden)} 个子块 unmapped", heartbeat_drag(app))

    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
