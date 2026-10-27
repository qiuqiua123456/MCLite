"""噪声太大，改用重复采样：同一状态测 3 轮取中位，比较「大图重绘」是不是主因。

home 页有一张 846x346 的 hero PNG 和头像，拖边框时整窗每帧重画，
大图重绘在慢机器上很贵。对照：
  1 现状
  2 hero canvas 换成纯色矩形（不贴图）
  3 hero canvas 整块 destroy
  4 现状复测（确认重复性）
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
REPEAT = 3


def drain(app, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.update()
        time.sleep(0.005)


def heartbeat_drag(app, start=1120, end=1300, step=4) -> dict:
    app.geometry(f"{start}x724")
    drain(app, 0.3)
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
    drain(app, 0.5)
    n = len(lateness)
    return {"mid": statistics.median(lateness), "p90": sorted(lateness)[int(n * 0.9)],
            "es": sum(1 for v in lateness if v > FRAME_BUDGET), "n": n}


def measure(app, tag: str) -> None:
    runs = [heartbeat_drag(app) for _ in range(REPEAT)]
    mids = [r["mid"] for r in runs]
    print(f"  {tag:24s} 中位 {statistics.median(mids):6.1f} ms"
          f"  (三轮 {', '.join(f'{m:.1f}' for m in mids)})"
          f" | 掉帧 {statistics.median([r['es'] for r in runs]):.0f}/47")


def find_hero(widget) -> list[tk.Widget]:
    """找出页面里所有贴了图片的 Canvas。"""
    out = []
    stack = [widget]
    while stack:
        w = stack.pop()
        if isinstance(w, tk.Canvas):
            try:
                if w.find_all() and any(w.type(i) == "image" for i in w.find_all()):
                    out.append(w)
            except tk.TclError:
                pass
        try:
            stack.extend(w.winfo_children())
        except tk.TclError:
            pass
    return out


def main() -> int:
    from mclite.ui import app as app_mod

    app = app_mod.App()
    app.create_pages()
    drain(app, 0.8)
    app.show_page("home")
    drain(app, 0.6)

    print("\n--- home 页 16ms 拖动，每档 3 轮取中位")
    measure(app, "1 现状")

    heroes = find_hero(app._pages["home"])
    print(f"     （找到 {len(heroes)} 个贴图 Canvas: "
          f"{[(h.winfo_width(), h.winfo_height()) for h in heroes]}）")

    # 2：把贴图项隐藏（只留背景色）
    saved = []
    for c in heroes:
        for i in c.find_all():
            if c.type(i) == "image":
                c.itemconfigure(i, state="hidden")
                saved.append((c, i))
    drain(app, 0.3)
    measure(app, "2 贴图项 hidden")

    for c, i in saved:
        c.itemconfigure(i, state="normal")
    drain(app, 0.3)

    # 3：整块 canvas destroy
    for c in heroes:
        c.pack_forget()
    drain(app, 0.3)
    measure(app, "3 大图 canvas 移出布局")

    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
