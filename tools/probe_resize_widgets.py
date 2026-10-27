"""拖动卡顿与「已映射控件数」的定量关系。

前面的探针已经把 Python 侧的开销全部排除掉了（顶栏 _draw 4ms、布局 27ms、
geometry 0ms），但心跳延迟还是 80ms。剩下的假设是：**Tk 在 Windows 上给每个
控件都建了一个真实子窗口（HWND）**，父窗口一改尺寸，系统就得逐个重定位并重绘
这些子窗口。若成立，卡顿应该与「已映射控件数」近似线性。

这个脚本用合成的 app 外壳（顶栏 Canvas + 左侧栏 + 容器页）验证：容器页里塞
N 个 Label，N = 0/30/60/120/240，分进程测每档的拖动心跳延迟。

用法：python tools/probe_resize_widgets.py 0|30|60|120|240
"""
from __future__ import annotations

import json
import statistics
import sys
import time
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mclite.ui import theme  # noqa: E402

WIDTH_START = 1120
WIDTH_END = 1300
STEP = 4
FRAME_MS = 16


def build(n_labels: int) -> tk.Tk:
    root = tk.Tk()
    root.geometry("1160x724")
    root.configure(bg=theme.BG)

    bar = tk.Canvas(root, height=48, highlightthickness=0, bd=0, bg=theme.ACCENT_DARK)
    bar.pack(side="top", fill="x")
    theme.gradient(bar, 1160, 48, theme.ACCENT_DARK, theme.ACCENT_HOVER, steps=160, tag="topbg")

    body = tk.Frame(root, bg=theme.BG)
    body.pack(side="top", fill="both", expand=True)

    side = tk.Frame(body, width=232, bg=theme.BG_ALT)
    side.pack(side="left", fill="y")
    side.pack_propagate(False)
    for i in range(6):
        tk.Label(side, text=f"项 {i}", bg=theme.BG_ALT, fg=theme.FG).pack(anchor="w", padx=12, pady=4)

    container = tk.Frame(body, bg=theme.BG)
    container.pack(side="left", fill="both", expand=True)

    page = tk.Frame(container, bg=theme.BG)
    page.place(x=0, y=0, relwidth=1, relheight=1)

    for i in range(n_labels):
        row = tk.Frame(page, bg=theme.BG_ALT)
        row.pack(fill="x", padx=8, pady=2)
        tk.Label(row, text=f"版本 1.{i}.0", bg=theme.BG_ALT, fg=theme.FG).pack(side="left", padx=6)
        tk.Label(row, text="release", bg=theme.BG_ALT, fg=theme.FG_DIM).pack(side="left", padx=6)

    return root


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    root = build(n)
    root.update()
    time.sleep(0.5)

    widgets = len(root.winfo_children()) + sum(
        len(w.winfo_children()) for w in root.winfo_children()
    )

    delays: list[float] = []
    state = {"expect": None, "last": None}

    def beat() -> None:
        now = time.perf_counter()
        if state["last"] is not None:
            delays.append((now - state["last"]) * 1000.0)
        state["last"] = now
        root.after(FRAME_MS, beat)

    widths = list(range(WIDTH_START, WIDTH_END, STEP))

    def drive() -> None:
        for w in widths:
            t0 = time.perf_counter()
            root.geometry(f"{w}x724")
            root.update()
            rest = FRAME_MS / 1000.0 - (time.perf_counter() - t0)
            if rest > 0:
                time.sleep(rest)

    beat()
    time.sleep(0.15)
    drive()
    time.sleep(0.15)
    root.update()

    root.destroy()

    # 稳态 16ms 心跳：超过 16ms 的部分就是卡顿
    over = [max(0.0, d - FRAME_MS) for d in delays[3:]]
    mid = statistics.median(over) if over else 0.0
    worst = max(over) if over else 0.0
    print("{" + f'"n": {n}, "widgets": {widgets}, "mid": {mid:.1f}, "worst": {worst:.1f}, '
          f'"frames": {len(over)}' + "}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
