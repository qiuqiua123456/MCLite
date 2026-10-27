"""把切页耗时拆成 show_page / update_idletasks / update 三段，定位真实开销。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mclite.ui.app import App  # noqa: E402


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
    for _ in range(3):
        app.update_idletasks()
        app.update()

    # 预热：让下载页把版本清单和 103 行建好
    for key in ("install", "settings", "home"):
        section(app, key)

    page = app._pages["install"]
    print(f"下载页列表行数: {len(page._rows)}")

    for key in ("install", "settings", "home", "install", "settings", "home"):
        a, b, c = section(app, key)
        print(f"{key:<9} show={a:6.1f}  idle={b:6.1f}  paint={c:6.1f}  total={a+b+c:6.1f} ms")

    # 对照：把下载页列表临时清空，看切页是否变快
    print("— 清空下载页列表后的同页切换 —")
    for w in page._scroll.inner.winfo_children():
        w.destroy()
    app.update_idletasks()
    for key in ("install", "settings", "install"):
        a, b, c = section(app, key)
        print(f"{key:<9} show={a:6.1f}  idle={b:6.1f}  paint={c:6.1f}  total={a+b+c:6.1f} ms")

    app.destroy()


if __name__ == "__main__":
    main()
