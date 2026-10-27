"""顶栏渐变：160 个矩形 item vs 1 张 PhotoImage。

顶栏 `_draw()` 里 160 段渐变贡献 160 个 canvas item，Python 侧画一次只要
2.4ms，但 item 数一多，Windows 侧的创建/删除/重绘就贵。这里对比两种做法在
「宽度连续变化」时的时间，并在最后测拖动心跳。
"""
from __future__ import annotations

import statistics
import sys
import time
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mclite.ui.theme import gradient, mix  # noqa: E402

C1, C2 = "#0E5FB8", "#2B7CE0"
H = 48


def colors_for(width: int, steps: int) -> list[str]:
    out = []
    for i in range(steps):
        t = i / max(1, steps - 1)
        out.append(mix(C1, C2, t))
    return out


def make_image(canvas, width: int) -> tk.PhotoImage:
    """1 像素高的一行渐变，zoom 到整条顶栏高。zoom 是 C 实现，比逐像素 put 快。"""
    steps = max(2, min(width, 256))
    row = "{" + " ".join(colors_for(width, steps)) + "}"
    img = tk.PhotoImage(master=canvas, width=steps, height=1)
    img.put(row)
    if width != steps:
        img = img.zoom(width // steps + 1, H)
    else:
        img = img.zoom(1, H)
    return img


def bench_rects(root, widths) -> float:
    cv = tk.Canvas(root, height=H, highlightthickness=0, bg=C1)
    cv.pack(fill="x")
    times = []
    for w in widths:
        cv.delete("all")
        t0 = time.perf_counter()
        gradient(cv, w, H, C1, C2, steps=160, tag="bg")
        times.append((time.perf_counter() - t0) * 1000.0)
    cv.destroy()
    return statistics.median(times)


def bench_image(root, widths) -> float:
    cv = tk.Canvas(root, height=H, highlightthickness=0, bg=C1)
    cv.pack(fill="x")
    keep = []
    times = []
    for w in widths:
        cv.delete("all")
        t0 = time.perf_counter()
        img = make_image(cv, w)
        cv.create_image(0, 0, anchor="nw", image=img, tags="bg")
        times.append((time.perf_counter() - t0) * 1000.0)
        keep.append(img)                      # 防止被 GC
    cv.destroy()
    return statistics.median(times)


def main() -> int:
    root = tk.Tk()
    root.geometry("1160x300")
    root.update()
    widths = list(range(1120, 1300, 4))

    r = bench_rects(root, widths)
    i = bench_image(root, widths)

    print(f"160 个矩形   _draw 中位 {r:6.2f} ms   item 数 160")
    print(f"1 张 PhotoImage  _draw 中位 {i:6.2f} ms   item 数 1")
    print(f"比值 {r / max(i, 0.001):.1f}x")

    # item 数对重绘的影响
    for label, n in (("160 个 item", 160), ("1 个 item", 1)):
        cv = tk.Canvas(root, height=H, highlightthickness=0, bg=C1)
        cv.pack(fill="x")
        for k in range(n):
            cv.create_rectangle(k, 0, k + 1, H, fill=mix(C1, C2, k / 160), outline="")
        root.update()
        t0 = time.perf_counter()
        for _ in range(20):
            cv.configure(width=1160)
            root.update()
        dt = (time.perf_counter() - t0) * 1000.0 / 20
        print(f"{label:12s} 改宽度+重绘 {dt:6.2f} ms")
        cv.destroy()
        root.update()

    root.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
