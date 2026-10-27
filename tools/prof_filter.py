"""定位「切换类型筛选」耗时为什么从 0.9ms 涨到 410ms。"""
from __future__ import annotations

import cProfile
import io
import pstats
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from smoke_install_filter import fake_versions  # noqa: E402


def pump(app, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.update_idletasks()
        app.update()
        time.sleep(0.01)


def main() -> int:
    from mclite.ui.app import App
    from mclite.ui.page_install import ALL_FAMILY

    app = App()
    app.create_pages()
    pump(app, 0.6)
    app.show_page("install")
    pump(app, 0.5)
    page = app._pages["install"]
    page._loading = False
    page._on_manifest(fake_versions())
    pump(app, 0.4)

    print("页面尺寸:", page.winfo_width(), page.winfo_height())
    print("容器尺寸:", app._container.winfo_width(), app._container.winfo_height())
    print("行数:", len(page._rows))

    # 拆开量：只跑 _set_filter（同步部分）
    for _ in range(3):
        t0 = time.perf_counter()
        page._set_filter("release")
        t1 = time.perf_counter()
        app.update_idletasks()
        t2 = time.perf_counter()
        app.update()
        t3 = time.perf_counter()
        print(f"  _set_filter {(t1-t0)*1000:7.1f} | update_idletasks {(t2-t1)*1000:7.1f} "
              f"| update {(t3-t2)*1000:7.1f} ms")
        page._set_filter(None)
        app.update_idletasks()
        app.update()

    print("\n=== 再用 after(1) 渲染路径量一次")
    for _ in range(3):
        t0 = time.perf_counter()
        page._set_filter("release")
        # 把 after(1) 排的渲染跑掉
        app.update()
        t1 = time.perf_counter()
        print(f"  filter(含after渲染) {(t1-t0)*1000:7.1f} ms  行数={len(page._rows)}")
        page._set_filter(None)
        app.update()

    print("\n=== cProfile：20 次 _set_filter + update")
    pr = cProfile.Profile()
    pr.enable()
    for _ in range(20):
        page._set_filter("release")
        app.update()
        page._set_filter(None)
        app.update()
    pr.disable()
    s = io.StringIO()
    pstats.Stats(pr, stream=s).sort_stats("cumulative").print_stats(18)
    print(s.getvalue())

    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
