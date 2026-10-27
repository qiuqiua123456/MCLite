"""重建 16 行时，ScrollFrame 到底收到了多少次 Configure / flush，布局跑了几轮。"""
from __future__ import annotations

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

    app = App()
    app.create_pages()
    pump(app, 0.6)
    app.show_page("install")
    pump(app, 0.5)
    page = app._pages["install"]
    page._loading = False
    page._on_manifest(fake_versions())
    pump(app, 0.4)
    sf = page._scroll
    inner = sf.inner

    counters = {"inner_cfg": 0, "canvas_cfg": 0, "region": 0, "width": 0}
    orig_region = sf._flush_region
    orig_width = sf._flush_width

    def region():
        counters["region"] += 1
        return orig_region()

    def width():
        counters["width"] += 1
        return orig_width()

    sf._flush_region = region
    sf._flush_width = width
    inner.bind("<Configure>", lambda e: counters.__setitem__(
        "inner_cfg", counters["inner_cfg"] + 1), add="+")
    sf._canvas.bind("<Configure>", lambda e: counters.__setitem__(
        "canvas_cfg", counters["canvas_cfg"] + 1), add="+")

    for i in range(4):
        page._filter = None if i % 2 else "release"
        page._render_sig = None
        for k in counters:
            counters[k] = 0
        t0 = time.perf_counter()
        page._render_now()
        t1 = time.perf_counter()
        app.update_idletasks()
        t2 = time.perf_counter()
        app.update()
        t3 = time.perf_counter()
        t4 = time.perf_counter()
        app.update_idletasks()
        t5 = time.perf_counter()
        print(f"[{i}] render {1000*(t1-t0):6.1f} | idle {1000*(t2-t1):7.1f} "
              f"| draw {1000*(t3-t2):7.1f} | 空 idle {1000*(t5-t4):5.1f} ms "
              f"| rows={len(page._rows):2d} | {counters}")

    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
