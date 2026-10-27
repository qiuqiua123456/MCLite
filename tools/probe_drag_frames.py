"""模拟真实拖动：连续微调窗口宽度，看每一帧花多久、页面跟不跟得上。

用户拖边框时 Windows 会连续发 WM_SIZE（约 60 次/秒），所以体感取决于
「每帧处理一次尺寸变化要多久」——不是「松手后多久跟上」。这个脚本按
16ms 间隔、每次 +2px 拖过去，记录每帧耗时和页面宽度的跟随情况。

对照四种状态，定位成本到底在哪一层：
  1 现状
  2 页面 place_forget（只剩外壳）
  3 现状但顶栏不重画（_draw 换空函数）
  4 现状但左侧栏不参与重排（pack_forget）
"""
from __future__ import annotations

import statistics
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


def drag(app, page, start=1120, end=1300, step=4, delay=0.016) -> dict:
    """按 16ms 节奏把宽度从 start 拖到 end，返回每帧耗时与跟随误差。"""
    widths = list(range(start, end + 1, step))
    app.geometry(f"{start}x724")
    pump(app, 0.3)

    frame_cost, lag = [], []
    for w in widths:
        t0 = time.perf_counter()
        app.geometry(f"{w}x724")
        app.update_idletasks()
        app.update()
        frame_cost.append((time.perf_counter() - t0) * 1000.0)
        if page is not None:
            try:
                lag.append(abs(page.winfo_width() - app._container.winfo_width()))
            except Exception:                  # noqa: BLE001
                pass
        time.sleep(delay)
    pump(app, 0.4)
    return {
        "mid": statistics.median(frame_cost),
        "worst": max(frame_cost),
        "over16": sum(1 for c in frame_cost if c > 16.6),
        "n": len(frame_cost),
        "lag": statistics.median(lag) if lag else 0,
        "lag_max": max(lag) if lag else 0,
    }


def show(tag: str, r: dict) -> None:
    print(f"  {tag:24s} 中位 {r['mid']:6.1f} 最慢 {r['worst']:6.1f} ms"
          f" | 超 16.6ms 的帧 {r['over16']:2d}/{r['n']}"
          f" | 页面误差 中位 {r['lag']:5.0f} 最大 {r['lag_max']:5.0f} px")


def main() -> int:
    from mclite.ui import app as app_mod

    app = app_mod.App()
    app.create_pages()
    pump(app, 0.8)
    app.show_page("home")
    pump(app, 0.6)
    page = app._pages["home"]

    print("\n--- home 页拖动 1120→1300，每帧 4px")
    show("1 现状", drag(app, page))

    pages = list(app._pages.values())
    for p in pages:
        p.place_forget()
    pump(app, 0.3)
    show("2 页面 place_forget", drag(app, None))
    app.show_page("home")
    pump(app, 0.5)

    bar = app._topbar
    real_draw = bar._draw
    bar._draw = lambda *a, **k: None
    show("3 顶栏不重画", drag(app, page))
    bar._draw = real_draw

    app._side.pack_forget()
    pump(app, 0.3)
    show("4 去掉左侧栏", drag(app, page))
    app._side.pack(before=app._container.master.winfo_children()[1] if False else None) if False else None

    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
