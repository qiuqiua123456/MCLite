"""给收尾那一帧（松手后约 100 ms 的那一帧）打点，看是谁花的钱。

`probe_settle_spike.py` 显示 install 页每轮 settle 总 390–400 ms，其中
首帧 update ~200 ms（Windows 整窗重绘），之后总有一次 ~100 ms 的帧。
这里把候选嫌疑人都包上计时：
  - `ScrollFrame._flush_width`（itemconfigure 改 inner 宽度 → 整块重排）
  - `ScrollFrame._auto_scrollbar`
  - `App._flush_page_size` / `_place_page` / `_drop_snapshot`
  - `page.on_resize`
  - `responsive.fix_clipped`
每次调用耗时 > 5 ms 就打一行；另外每帧记录总耗时。

用法：python tools/probe_settle_after.py [page] [rounds]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

HOT_MS = 5.0


def wrap(obj, attr: str, label: str, sink: list) -> None:
    orig = getattr(obj, attr, None)
    if orig is None:
        return

    def patched(*a, **k):
        t = time.perf_counter()
        try:
            return orig(*a, **k)
        finally:
            dt = (time.perf_counter() - t) * 1000.0
            if dt > HOT_MS:
                sink.append((label, round(dt, 1)))

    setattr(obj, attr, patched)


def main() -> None:
    from mclite.ui import responsive, theme
    from mclite.ui.app import App

    page_name = sys.argv[1] if len(sys.argv) > 1 else "install"
    rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    sink: list = []

    wrap(theme.ScrollFrame, "_flush_width", "ScrollFrame._flush_width", sink)
    wrap(theme.ScrollFrame, "_auto_scrollbar", "ScrollFrame._auto_scrollbar", sink)
    wrap(theme.ScrollFrame, "_flush_region", "ScrollFrame._flush_region", sink)
    wrap(theme.ScrollFrame, "_flush_scrollbar", "ScrollFrame._flush_scrollbar", sink)
    wrap(App, "_flush_page_size", "App._flush_page_size", sink)
    wrap(App, "_place_page", "App._place_page", sink)
    wrap(App, "_drop_snapshot", "App._drop_snapshot", sink)
    wrap(App, "_ensure_snapshot", "App._ensure_snapshot", sink)
    wrap(App, "_run_resize", "App._run_resize", sink)
    wrap(responsive, "fix_clipped", "responsive.fix_clipped", sink)
    wrap(responsive, "wrap_labels", "responsive.wrap_labels", sink)

    app = App()
    app.create_pages()
    try:
        app._pages["install"].load_manifest = lambda *a, **k: None
    except (KeyError, AttributeError):
        pass
    end = time.time() + 1.0
    while time.time() < end:
        app.update()
        time.sleep(0.01)
    page = app._pages[page_name]
    wrap(page, "on_resize", f"{page_name}.on_resize", sink)
    app.show_page(page_name)
    end = time.time() + 0.5
    while time.time() < end:
        app.update()
        time.sleep(0.01)

    for i in range(rounds):
        app.geometry("1160x724")
        app.update_idletasks()
        app.update()
        end = time.time() + 0.3
        while time.time() < end:
            app.update()
            time.sleep(0.01)

        sink.clear()
        app.geometry("1290x724")
        t0 = time.perf_counter()
        frame = 0
        while time.perf_counter() - t0 < 3.0:
            f0 = time.perf_counter()
            app.update()
            frame += 1
            dt = (time.perf_counter() - f0) * 1000.0
            if dt > 20:
                print(f"  帧 {frame} {dt:6.0f} ms  热点 {sink[-6:]}")
            if abs(page.winfo_width() - app._container.winfo_width()) <= 2:
                break
            time.sleep(0.004)
        total = (time.perf_counter() - t0) * 1000.0
        print(f"[{i}] 总 {total:6.1f} ms  热点 {sink}")
    app.destroy()


if __name__ == "__main__":
    main()
