"""在指定窗口尺寸下 dump 每个页面的控件几何，找出谁被挤出窗口。

跑法：G:\\python\\python.exe tools\\probe_small_geom.py [w] [h]
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def pump(app, sec: float) -> None:
    end = time.perf_counter() + sec
    while time.perf_counter() < end:
        try:
            app.update()
        except Exception:                            # noqa: BLE001
            return
        time.sleep(0.02)


def walk(w, depth=0, out=None):
    out = [] if out is None else out
    try:
        kids = w.winfo_children()
    except Exception:                                # noqa: BLE001
        return out
    for k in kids:
        try:
            if not k.winfo_ismapped():
                continue
            out.append((depth, k, k.winfo_x(), k.winfo_y(),
                        k.winfo_width(), k.winfo_height(),
                        k.winfo_class()))
        except Exception:                            # noqa: BLE001
            continue
        walk(k, depth + 1, out)
    return out


def main() -> int:
    w_in = int(sys.argv[1]) if len(sys.argv) > 1 else 880
    h_in = int(sys.argv[2]) if len(sys.argv) > 2 else 560

    from mclite.ui.app import App

    app = App()
    app.create_pages()
    app.show_page("home")
    pump(app, 1.0)

    for page_key in ("home", "install", "settings"):
        app.show_page(page_key)
        pump(app, 0.7)
        app.geometry(f"{w_in}x{h_in}+60+60")
        pump(app, 0.9)
        page = app._pages[page_key]
        pw, ph = page.winfo_width(), page.winfo_height()
        print(f"\n=== {page_key}  {app.winfo_width()}x{app.winfo_height()}  "
              f"page={pw}x{ph}", flush=True)
        worst = []
        for depth, k, x, y, w, h, cls in walk(page):
            right, bottom = x + w, y + h
            if right > pw + 1 or bottom > ph + 1:
                worst.append((cls, x, y, w, h, right - pw, bottom - ph,
                              str(k).split(".")[-1]))
        worst.sort(key=lambda t: -(t[6] + t[5]))
        print(f"  越界控件 {len(worst)} 个", flush=True)
        for cls, x, y, w, h, ow, oh, name in worst[:14]:
            print(f"    {cls:<10} {name:<14} x={x:4d} y={y:4d} "
                  f"{w:4d}x{h:4d}  超出右 {ow:4d} 超出下 {oh:4d}", flush=True)

    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
