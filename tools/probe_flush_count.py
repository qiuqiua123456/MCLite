"""决定性实验：拖动时 `_flush_page_size` 到底被触发了几次、每次花多久。

假设：`_on_container_configure` 用 70ms 防抖，但每帧渲染就要 80ms，
于是「事件间隔 > 70ms」恒成立 → 防抖每帧都到期 → 每帧都做一次整页重排
（~300ms）→ 下一帧更慢 → 防抖必然再次到期。自锁的卡顿环。
"""
from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

STEP_MS = 16


def drain(app, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.update()
        time.sleep(0.005)


def install_recorder(app):
    stat = {"n": 0, "total": 0.0, "worst": 0.0}
    real = app._flush_page_size

    def wrapped():
        t0 = time.perf_counter()
        real()
        cost = (time.perf_counter() - t0) * 1000.0
        stat["n"] += 1
        stat["total"] += cost
        stat["worst"] = max(stat["worst"], cost)

    app._flush_page_size = wrapped
    return stat


def drag(app, start=1120, end=1300, step=4, pace=STEP_MS) -> dict:
    app.geometry(f"{start}x724")
    drain(app, 0.4)
    widths = list(range(start, end + 1, step))
    lateness, it = [], {"i": 0, "last": time.perf_counter()}

    def beat():
        now = time.perf_counter()
        lateness.append(max(0.0, (now - it["last"]) * 1000.0 - STEP_MS))
        it["last"] = now
        i = it["i"]
        if i < len(widths):
            it["i"] = i + 1
            app.geometry(f"{widths[i]}x724")
            app.after(STEP_MS, beat)

    app.after(pace, beat)
    deadline = time.perf_counter() + 40
    while it["i"] < len(widths) and time.perf_counter() < deadline:
        app.update()
        time.sleep(0.002)
    drain(app, 0.8)
    n = len(lateness)
    return {"mid": statistics.median(lateness), "p90": sorted(lateness)[int(n * 0.9)],
            "worst": max(lateness), "n": n,
            "over": sum(1 for v in lateness if v > 16.6)}


def main() -> int:
    from mclite.ui import app as app_mod

    app = app_mod.App()
    app.create_pages()
    drain(app, 0.8)
    app.show_page("home")
    drain(app, 0.6)

    print("\n--- 拖动 1120→1300（46 帧），记录 _flush_page_size 触发次数与耗时")
    stat = install_recorder(app)
    r = drag(app)
    print(f"  心跳延迟 中位 {r['mid']:6.1f} p90 {r['p90']:6.1f} 最差 {r['worst']:7.1f} ms"
          f" | 掉帧 {r['over']}/{r['n']}")
    print(f"  _flush_page_size 触发 {stat['n']} 次"
          f" | 累计 {stat['total']:7.1f} ms | 单次最慢 {stat['worst']:6.1f} ms")

    # 把防抖拉长到 300ms，看是否只剩一次触发
    app._on_container_configure.__func__.__globals__  # noqa: B018  (确认可改)
    print("\n--- 同一次拖动，但把防抖窗口临时改成 300ms")
    stat2 = install_recorder(app)
    orig_after = app.after
    calls = {"n": 0}

    def after(ms, func=None, *a):
        calls["n"] += 1
        return orig_after(300 if ms == 70 else ms, func, *a) if func is not None else orig_after(ms)

    app.after = after
    r2 = drag(app)
    app.after = orig_after
    print(f"  心跳延迟 中位 {r2['mid']:6.1f} p90 {r2['p90']:6.1f} 最差 {r2['worst']:7.1f} ms"
          f" | 掉帧 {r2['over']}/{r2['n']}")
    print(f"  _flush_page_size 触发 {stat2['n']} 次"
          f" | 累计 {stat2['total']:7.1f} ms | 单次最慢 {stat2['worst']:6.1f} ms")

    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
