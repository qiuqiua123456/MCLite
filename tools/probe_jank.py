"""真实卡顿度量：跳帧（heartbeat lateness）。

前面几个 probe 都强制每帧 `update()` 同步重绘，测出来的是「同步重绘的代价」，
不是用户体感——真实拖动时 Windows 会合并 WM_PAINT，Tk 的布局也在 idle 里做。

这里改成：让主循环自然跑，一个 `after(16)` 的心跳报时，同时另一个定时器
每 16ms 改一次窗口宽度。心跳「本该 16ms 到、实际多少 ms 才到」的分布，
就是用户拖边框时感受到的卡顿。

对照四种状态，找出真正能降延迟的做法。
"""
from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

STEP_MS = 16
FRAME_BUDGET = 16.6


def drain(app, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.update()
        time.sleep(0.005)


def heartbeat_drag(app, start=1120, end=1300, step=4, on_step=None, on_done=None) -> dict:
    """按 16ms 节奏改宽度，同时用心跳量主循环延迟。"""
    app.geometry(f"{start}x724")
    drain(app, 0.35)

    widths = list(range(start, end + 1, step))
    lateness: list[float] = []
    it = {"i": 0, "last": time.perf_counter()}

    def beat():
        now = time.perf_counter()
        late = (now - it["last"]) * 1000.0 - STEP_MS
        lateness.append(max(0.0, late))
        it["last"] = now
        i = it["i"]
        if i < len(widths):
            it["i"] = i + 1
            if on_step:
                on_step(app, widths[i])
            else:
                app.geometry(f"{widths[i]}x724")
            app.after(STEP_MS, beat)
        else:
            if on_done:
                on_done(app)

    app.after(STEP_MS, beat)
    deadline = time.perf_counter() + 30
    while it["i"] < len(widths) and time.perf_counter() < deadline:
        app.update()
        time.sleep(0.003)
    drain(app, 0.6)
    n = len(lateness)
    return {
        "mid": statistics.median(lateness) if lateness else 0.0,
        "p90": sorted(lateness)[int(n * 0.9)] if lateness else 0.0,
        "worst": max(lateness) if lateness else 0.0,
        "n": n,
        "over": sum(1 for v in lateness if v > FRAME_BUDGET),
    }


def show(tag: str, r: dict) -> None:
    print(f"  {tag:26s} 心跳延迟 中位 {r['mid']:6.1f} p90 {r['p90']:6.1f}"
          f" 最差 {r['worst']:7.1f} ms | 掉帧 {r['over']:2d}/{r['n']}")


def main() -> int:
    from mclite.ui import app as app_mod

    app = app_mod.App()
    app.create_pages()
    drain(app, 0.8)
    app.show_page("home")
    drain(app, 0.6)
    page = app._pages["home"]

    print("\n--- home 页，16ms 一步拖动 1120→1300（每步 4px）")
    show("1 现状", heartbeat_drag(app, ))

    # 2：拖动全程把页面 place_forget，松手再放回来（内容暂时冻结，但边框跟手）
    def hide(app_, w):
        page.place_forget()

    def restore(app_):
        app_._place_page(page, app_._container.winfo_width(), app_._container.winfo_height())

    show("2 拖动中隐藏页面", heartbeat_drag(app, on_step=hide, on_done=restore))

    # 3：只让顶栏不重画
    bar = app._topbar
    real = bar._draw
    bar._draw = lambda *a, **k: None
    show("3 顶栏不重画", heartbeat_drag(app))
    bar._draw = real

    # 4：页面用 relwidth 相对尺寸（让 Tk 自己跟，不走 70ms 防抖）
    def rel(app_):
        for p in app._pages.values():
            p.place_configure(relwidth=1, relheight=1, width=0, height=0)

    rel(app)
    drain(app, 0.3)
    show("4 页面改回相对尺寸", heartbeat_drag(app))
    app.show_page("home")
    drain(app, 0.4)

    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
