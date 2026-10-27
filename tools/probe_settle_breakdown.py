"""把「松手到页面跟上」这 300ms 拆开：防抖 / 布局 / 重绘各占多少。

不看清楚就改代码等于猜。逐阶段打点：
  T0 改窗口宽度
  T1 第一次 update_idletasks 完（窗口自身几何）
  T2 防抖 70ms 到期、页面被 place 成新尺寸
  T3 页面子树重排完
  T4 整窗重绘完
"""
from __future__ import annotations

import sys
import time
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


def main() -> int:
    from mclite.ui.app import App

    app = App()
    app.create_pages()
    pump(app, 0.8)

    for name in ("home", "install", "settings"):
        app.show_page(name)
        pump(app, 0.5)
        page = app._pages[name]

        print(f"\n=== {name}  页面 {page.winfo_width()}x{page.winfo_height()}")

        for target in (1000, 1240):
            app.geometry(f"{1160}x724")
            pump(app, 0.5)

            # 记录各阶段
            marks = {}
            t0 = time.perf_counter()
            app.geometry(f"{target}x724")
            app.update_idletasks()
            marks["窗口几何"] = (time.perf_counter() - t0) * 1000

            # 一直泵，直到页面宽度跟上
            t_flu = t_place = t_draw = 0.0
            seen_width = page.winfo_width()
            deadline = time.perf_counter() + 5.0
            while time.perf_counter() < deadline:
                f0 = time.perf_counter()
                app.update_idletasks()
                d_idle = (time.perf_counter() - f0) * 1000
                f1 = time.perf_counter()
                app.update()
                d_draw = (time.perf_counter() - f1) * 1000
                if abs(page.winfo_width() - app._container.winfo_width()) <= 2:
                    if page.winfo_width() != seen_width:
                        t_flu += d_idle
                        t_draw += d_draw
                    break
                if page.winfo_width() != seen_width:
                    seen_width = page.winfo_width()
                t_flu += d_idle
                t_draw += d_draw
                time.sleep(0.005)
            total = (time.perf_counter() - t0) * 1000
            print(f"  宽 {target}: 总 {total:6.0f} ms | 窗口几何 {marks['窗口几何']:5.1f}"
                  f" | 累计 idle {t_flu:6.1f} | 累计 draw {t_draw:6.1f}")

    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
