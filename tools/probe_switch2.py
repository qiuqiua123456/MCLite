"""精确测量切页成本：等版本清单真的加载完、行数稳定后再计时。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mclite.ui.app import App  # noqa: E402


def pump(app, seconds=0.3):
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.update_idletasks()
        app.update()
        time.sleep(0.005)


def section(app, key):
    t = time.perf_counter()
    app.show_page(key)
    t_show = (time.perf_counter() - t) * 1000
    t = time.perf_counter()
    app.update_idletasks()
    t_idle = (time.perf_counter() - t) * 1000
    t = time.perf_counter()
    app.update()
    t_paint = (time.perf_counter() - t) * 1000
    return t_show, t_idle, t_paint


def main() -> None:
    app = App()
    app.create_pages()
    pump(app, 0.5)

    page = app._pages["install"]
    # 等清单加载完成
    for _ in range(100):
        pump(app, 0.1)
        if page._rows:
            break
    print(f"下载页行数 = {len(page._rows)}，版本总数 = {len(page._all)}")

    pump(app, 0.5)

    print("— 稳态（行已建好）—")
    for key in ("install", "settings", "home", "install", "settings", "home",
                "install", "settings", "home"):
        a, b, c = section(app, key)
        rows = len(page._rows)
        print(f"{key:<9} show={a:6.1f} idle={b:6.1f} paint={c:6.1f} "
              f"total={a+b+c:7.1f} ms  rows={rows}")

    print(f"dnd 已登记控件数 = {len(app._dnd_registered)}")
    app.destroy()


if __name__ == "__main__":
    main()
