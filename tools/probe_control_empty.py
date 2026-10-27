"""控制实验：一个空 Tk 窗口连续做 5 轮同样的拖动，看数字会不会一轮比一轮差。

如果空窗口也逐轮恶化，说明「同一进程里重复拖动」这个测量方法本身在漂移，
前面那些「隐藏页面反而更慢」的结论就不可信，必须换方法（每档独立进程）。
"""
from __future__ import annotations

import statistics
import sys
import time
import tkinter as tk

STEP_MS = 16


def drain(root, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        root.update()
        time.sleep(0.005)


def drag(root, start=1120, end=1300, step=4) -> dict:
    root.geometry(f"{start}x724")
    drain(root, 0.3)
    widths = list(range(start, end + 1, step))
    lateness, it = [], {"i": 0, "last": time.perf_counter()}

    def beat():
        now = time.perf_counter()
        lateness.append(max(0.0, (now - it["last"]) * 1000.0 - STEP_MS))
        it["last"] = now
        i = it["i"]
        if i < len(widths):
            it["i"] = i + 1
            root.geometry(f"{widths[i]}x724")
            root.after(STEP_MS, beat)

    root.after(STEP_MS, beat)
    deadline = time.perf_counter() + 30
    while it["i"] < len(widths) and time.perf_counter() < deadline:
        root.update()
        time.sleep(0.002)
    drain(root, 0.5)
    return {"mid": statistics.median(lateness), "worst": max(lateness)}


def main() -> int:
    root = tk.Tk()
    root.geometry("1160x724")
    cv = tk.Canvas(root, bg="#0E5FB8", highlightthickness=0)
    cv.pack(fill="both", expand=True)
    drain(root, 0.6)

    print("\n--- 空窗口（只有一个纯色 Canvas）连续 5 轮相同拖动")
    for i in range(5):
        r = drag(root)
        print(f"  轮 {i + 1}: 心跳延迟 中位 {r['mid']:6.1f} 最差 {r['worst']:7.1f} ms")

    root.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
