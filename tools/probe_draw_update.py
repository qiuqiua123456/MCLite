"""单帧口径：改宽度 → _draw() → update()，量这一帧的真实成本。

拖动测法噪声太大（同一状态三轮能差 2.4 倍），这里只量「一帧」，
但**包含重绘**（update），因此能把「画图 vs 重绘」分开：
  A 只 _draw 不 update  → 纯画图成本
  B _draw 再 update     → 画图 + 重绘
B - A 就是 Windows/Tk 的重绘成本。
"""
from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

WIDTHS = (1128, 1132, 1136, 1140, 1144, 1148, 1152, 1156, 1160, 1164)


def drain(app, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.update()
        time.sleep(0.005)


def frame_costs(app, rounds=3) -> tuple[float, float, float]:
    """返回 (draw_only, draw+update, update_only) 的中位毫秒。"""
    draw_only, both, upd_only = [], [], []
    for _ in range(rounds):
        for w in WIDTHS:
            app.geometry(f"{w}x724")
            app.update_idletasks()
            app.update()
            # A: 只 _draw
            t0 = time.perf_counter()
            app._topbar._draw()
            draw_only.append((time.perf_counter() - t0) * 1000.0)
            app.update()
            # B: _draw + update
            t0 = time.perf_counter()
            app._topbar._draw()
            app.update()
            both.append((time.perf_counter() - t0) * 1000.0)
            # C: 只 update（无脏区）
            t0 = time.perf_counter()
            app.update()
            upd_only.append((time.perf_counter() - t0) * 1000.0)
    return (statistics.median(draw_only), statistics.median(both),
            statistics.median(upd_only))


def report(tag: str, app) -> None:
    a, b, c = frame_costs(app)
    print(f"  {tag:24s} 只画图 {a:6.2f} | 画图+重绘 {b:7.2f} | 纯 update {c:5.2f} ms")


def main() -> int:
    from mclite.ui import app as app_mod
    from mclite.ui import theme as theme_mod

    app = app_mod.App()
    app.create_pages()
    drain(app, 0.8)
    app.show_page("home")
    drain(app, 0.6)
    bar = app._topbar

    print("\n--- home 页，改宽度后一帧的成本（每档 3 轮 × 10 个宽度取中位）")
    report("1 现状", app)

    # 2：渐变降到 24 段
    orig_gradient = theme_mod.gradient
    app_mod.gradient = lambda canvas, w, h, c1, c2, steps=110, tag="grad": \
        orig_gradient(canvas, w, h, c1, c2, steps=24, tag=tag)
    report("2 渐变 24 段", app)
    app_mod.gradient = orig_gradient

    # 3：不画文字
    real_text = bar.create_text
    bar.create_text = lambda *a, **k: 0
    report("3 不画文字", app)
    bar.create_text = real_text

    # 4：把整个 _draw 换成只画一条矩形
    real_draw = bar._draw

    def flat():
        bar.delete("all")
        bar.create_rectangle(0, 0, bar.winfo_width(), bar.winfo_height(),
                             fill="#0E5FB8", outline="")

    bar._draw = flat
    report("4 只画一条矩形", app)
    bar._draw = real_draw

    # 5：完全不动顶栏
    bar._draw = lambda: None
    report("5 顶栏不重画", app)
    bar._draw = real_draw

    print(f"\n  顶栏当前 item 数 {len(bar.find_all())}")
    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
