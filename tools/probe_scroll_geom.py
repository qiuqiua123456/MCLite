"""看下载页 ScrollFrame 修复后的真实几何：内层是否还比画布宽。"""
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
    print("page      ", page.winfo_width(), "x", page.winfo_height())
    print("scrollframe", sf.winfo_width(), "x", sf.winfo_height())
    print("canvas    ", sf._canvas.winfo_width(), "x", sf._canvas.winfo_height())
    print("inner     ", sf.inner.winfo_width(), "x", sf.inner.winfo_height())
    print("item width", sf._canvas.itemcget(sf._win, "width"))
    print("item height", sf._canvas.itemcget(sf._win, "height"))
    print("scrollregion", sf._canvas.cget("scrollregion"))
    print("_win_w 缓存", getattr(sf, "_win_w", None))
    print("行数", len(page._rows))

    # 量一次纯重绘：不动任何东西
    for _ in range(4):
        app.update_idletasks()
        t0 = time.perf_counter()
        app.update()
        print(f"  空 update {(time.perf_counter()-t0)*1000:7.1f} ms")

    # 换筛选后重绘
    for _ in range(3):
        t0 = time.perf_counter()
        page._set_filter("release")
        app.update()
        print(f"  filter release {(time.perf_counter()-t0)*1000:7.1f} ms")
        t0 = time.perf_counter()
        page._set_filter(None)
        app.update()
        print(f"  filter all     {(time.perf_counter()-t0)*1000:7.1f} ms")

    print("\n修复后 inner 宽度:", sf.inner.winfo_width(),
          " 画布宽:", sf._canvas.winfo_width())
    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
