"""切页耗时实测：区分「首次绘制」和「来回切换」的稳态开销。

用户反馈「切换页面比较卡」，需要知道稳态（第二次以后）到底多少毫秒。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mclite.ui.app import App  # noqa: E402


def main() -> None:
    app = App()
    app.create_pages()
    for _ in range(3):
        app.update_idletasks()
        app.update()

    keys = ["install", "settings", "home"]

    print("— 首次切到各页（含首次绘制）—")
    for key in keys:
        t = time.perf_counter()
        app.show_page(key)
        app.update_idletasks()
        t1 = (time.perf_counter() - t) * 1000
        t = time.perf_counter()
        app.update()
        t2 = (time.perf_counter() - t) * 1000
        print(f"{key:<9} show={t1:6.1f} ms  paint={t2:6.1f} ms")

    print("— 稳态：来回切换 12 次 —")
    samples: dict[str, list[float]] = {k: [] for k in keys}
    order = (keys * 4)
    for key in order:
        t = time.perf_counter()
        app.show_page(key)
        app.update_idletasks()
        app.update()
        samples[key].append((time.perf_counter() - t) * 1000)

    for key in keys:
        vals = samples[key][1:]          # 丢掉第一轮
        if not vals:
            continue
        avg = sum(vals) / len(vals)
        print(f"{key:<9} avg={avg:6.1f} ms   max={max(vals):6.1f} ms   n={len(vals)}")

    app.destroy()


if __name__ == "__main__":
    main()
