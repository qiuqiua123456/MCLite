"""底线实验：一个「什么都没有」的 Tk 窗口，改一次宽度要多久？

用来判断 300ms 到底是我们的控件树造成的，还是这台机器/Tk 本身的固定成本。
对照四档：空窗口 / 一个 Label / 一个 Canvas 贴图 / 1080p 全屏纯色。
"""
from __future__ import annotations

import statistics
import sys
import time
import tkinter as tk

WIDTHS = (1000, 1240, 1080, 1400, 1160, 1160)


def pump(root, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        root.update_idletasks()
        root.update()
        time.sleep(0.005)


def measure(root, tag: str) -> None:
    """改宽度 → 只 update_idletasks（布局）→ 只 update（重绘）。"""
    layouts, draws = [], []
    for w in WIDTHS:
        root.geometry(f"{w}x724")
        t0 = time.perf_counter()
        root.update_idletasks()
        layouts.append((time.perf_counter() - t0) * 1000.0)
        t1 = time.perf_counter()
        root.update()
        draws.append((time.perf_counter() - t1) * 1000.0)
        time.sleep(0.02)
    print(f"  {tag:22s} 布局 中位 {statistics.median(layouts):6.1f} 最慢 {max(layouts):6.1f}"
          f" | 重绘 中位 {statistics.median(draws):6.1f} 最慢 {max(draws):6.1f} ms")


def main() -> int:
    root = tk.Tk()
    root.geometry("1160x724")
    pump(root, 0.6)

    print("Tk 版本:", root.tk.call("info", "patchlevel"), "| scaling", root.tk.call("tk", "scaling"))
    measure(root, "空窗口（无子控件）")

    lab = tk.Label(root, text="hello")
    lab.pack()
    pump(root, 0.3)
    measure(root, "挂一个 Label")
    lab.pack_forget()

    cv = tk.Canvas(root, bg="#0E5FB8", highlightthickness=0)
    cv.pack(fill="both", expand=True)
    pump(root, 0.3)
    measure(root, "全屏 Canvas 纯色")
    cv.pack_forget()

    # 100 个 Label，模拟「控件多」
    box = tk.Frame(root)
    box.pack(fill="both", expand=True)
    for i in range(100):
        tk.Label(box, text=f"行 {i}").pack(fill="x")
    pump(root, 0.4)
    measure(root, "100 个 Label")

    root.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
