"""直接给 TopBar._draw() 单次调用计时，逐项拆开看谁贵。

心跳法只能看整体，这里直接测一次 _draw 要多久、里面哪一句话贵。
不用心跳、不拖动，纯粹量函数调用成本，噪声最小。
"""
from __future__ import annotations

import statistics
import sys
import time
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REPEAT = 30


def drain(app, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.update()
        time.sleep(0.005)


def timeit(fn, repeat=REPEAT) -> tuple[float, float]:
    samples = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000.0)
    return statistics.median(samples), max(samples)


def main() -> int:
    from mclite.ui import app as app_mod
    from mclite.ui import theme as theme_mod

    app = app_mod.App()
    app.create_pages()
    drain(app, 0.8)
    app.show_page("home")
    drain(app, 0.6)
    bar = app._topbar
    print(f"顶栏尺寸 {bar.winfo_width()}x{bar.winfo_height()}，"
          f"当前 item 数 {len(bar.find_all())}")

    mid, worst = timeit(bar._draw)
    print(f"\n_draw() 整体            中位 {mid:7.2f} 最慢 {worst:7.2f} ms"
          f"  （调用后 item 数 {len(bar.find_all())}）")

    # 拆：只 delete + 只渐变
    def only_clear():
        bar.delete("all")

    mid, _ = timeit(only_clear)
    print(f"  delete all            中位 {mid:7.2f} ms")

    def only_gradient():
        theme_mod.gradient(bar, bar.winfo_width(), bar.winfo_height(),
                           theme_mod.ACCENT_DARK, theme_mod.ACCENT_HOVER,
                           steps=160, tag="probeGrad")
        bar.delete("probeGrad")

    mid, _ = timeit(only_gradient)
    print(f"  160 段渐变            中位 {mid:7.2f} ms")

    # create_text 单项成本（用同一个 Font 对象）
    for tag, font in (("_f_logo", bar._f_logo), ("_f_brand", bar._f_brand),
                      ("_f_nav", bar._f_nav), ("_f_nav_b", bar._f_nav_b),
                      ("_f_small", bar._f_small)):
        def one_text(f=font):
            i = bar.create_text(10, 10, text="测试", font=f, tags="probeText")
            bar.delete("probeText")

        mid, _ = timeit(one_text)
        print(f"  create_text {tag:9s} 中位 {mid:7.2f} ms")

    # 同样内容、改成元组字体
    def one_text_tuple():
        i = bar.create_text(10, 10, text="MCLite",
                            font=("Microsoft YaHei UI", 10), tags="probeText")
        bar.delete("probeText")

    mid, _ = timeit(one_text_tuple)
    print(f"  create_text 元组字体   中位 {mid:7.2f} ms")

    # measure() 成本
    mid, _ = timeit(lambda: bar._f_brand.measure("MCLite"))
    print(f"  Font.measure()        中位 {mid:7.2f} ms")

    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
