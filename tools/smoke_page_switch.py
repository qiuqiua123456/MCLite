"""回归：页面切换耗时（用户反馈「切换页面比较卡」）。

只测界面切换本身，不含网络。判据：每次都应在 120 ms 内完成，
首次进入某页允许更慢（要建控件）。
"""

from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PAGES = ("home", "install", "settings")
BUDGET_MS = 120.0


def pump(app, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.update_idletasks()
        app.update()
        time.sleep(0.01)


def timed_switch(app, name: str) -> float:
    t0 = time.perf_counter()
    app.show_page(name)
    app.update_idletasks()
    return (time.perf_counter() - t0) * 1000.0


def main() -> int:
    from mclite.ui.app import App

    app = App()
    app.create_pages()
    pump(app, 0.6)

    fails = 0
    # 预热一轮，让所有页面都建过一次
    for p in PAGES:
        timed_switch(app, p)
        pump(app, 0.15)

    for p in PAGES:
        samples = [timed_switch(app, p) for _ in range(5)]
        pump(app, 0.15)
        med = statistics.median(samples)
        worst = max(samples)
        ok = med <= BUDGET_MS
        fails += 0 if ok else 1
        print(f"{'PASS' if ok else 'FAIL'}  {p:9s} 中位 {med:6.1f} ms  最慢 {worst:6.1f} ms  "
              f"样本 {[round(s) for s in samples]}")

    # 页内页签切换（开始页 启动 / 模组 / 账户）
    home = app._pages["home"]
    app.show_page("home")
    pump(app, 0.3)
    tabs = getattr(home, "_tabs", None)
    if tabs is not None:
        for key in ("launch", "mods", "account"):
            t0 = time.perf_counter()
            tabs.set(key, fire=True)
            app.update_idletasks()
            ms = (time.perf_counter() - t0) * 1000.0
            ok = ms <= BUDGET_MS
            fails += 0 if ok else 1
            print(f"{'PASS' if ok else 'FAIL'}  home/{key:9s} {ms:6.1f} ms")
            pump(app, 0.15)

    app.destroy()
    print()
    print("ALL PASS" if not fails else f"{fails} 项超预算")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
