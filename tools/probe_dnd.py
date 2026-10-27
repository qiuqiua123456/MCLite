"""微测试：add_drop_target 的去重是否真的生效。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mclite.ui.app import App  # noqa: E402


def main() -> None:
    app = App()
    app.create_pages()
    app.update_idletasks()
    app.show_page("install")
    app.update()

    page = app._pages["install"]
    n0 = len(app._dnd_registered)

    t = time.perf_counter()
    app.add_drop_target(page)
    d1 = (time.perf_counter() - t) * 1000
    n1 = len(app._dnd_registered)

    t = time.perf_counter()
    app.add_drop_target(page)
    d2 = (time.perf_counter() - t) * 1000
    n2 = len(app._dnd_registered)

    print(f"after show: registered={n0}")
    print(f"call1 {d1:7.1f} ms -> {n1}")
    print(f"call2 {d2:7.1f} ms -> {n2}")
    print(f"total widgets on page: {len(page.winfo_children())} direct children")

    # 逐页面统计耗时
    for key in ("home", "install", "settings"):
        app.show_page(key)
        app.update()
        p = app._pages[key]
        t = time.perf_counter()
        app.add_drop_target(p)
        print(f"{key:<9} re-register {((time.perf_counter()-t)*1000):7.1f} ms")

    app.destroy()


if __name__ == "__main__":
    main()
