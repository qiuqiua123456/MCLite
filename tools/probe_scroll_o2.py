"""验证假设：重建时每加一行都触发 ScrollFrame 的 scrollregion 重算（O(n²)）。

对比三种情况下建 400 行 + 3 组标题的总耗时：
  A. 现状
  B. 期间把 _flush_region / _flush_width 屏蔽（模拟「批量构建」）
  C. 直接建到普通 Frame（不走 Canvas 窗口）
"""
from __future__ import annotations

import sys
import time
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mclite.versionmeta import VersionSummary  # noqa: E402


def pump(app, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        try:
            app.update_idletasks()
            app.update()
        except Exception:                          # noqa: BLE001
            return
        time.sleep(0.005)


def big_manifest(n=920):
    out = []
    for i in range(n):
        if i % 3 == 0:
            out.append(VersionSummary(f"1.{21 - i % 5}.{4 - i % 4}", "release", "",
                                      "2024-01-01T00:00:00+00:00"))
        elif i % 3 == 1:
            out.append(VersionSummary(f"24w{14 - i % 20:02d}a", "snapshot", "",
                                      "2024-01-01T00:00:00+00:00"))
        else:
            out.append(VersionSummary(f"1.{21 - i % 5}-pre{i % 9 + 1}", "snapshot", "",
                                      "2024-01-01T00:00:00+00:00"))
    return out


def main() -> int:
    from mclite.ui.app import App

    app = App()
    app.create_pages()
    pump(app, 0.6)
    app.show_page("install")
    pump(app, 0.5)
    page = app._pages["install"]
    page._loading = False
    page._all = big_manifest(920)
    page._filter = None
    page._family = "全部版本"
    sf = page._scroll

    def run(tag: str) -> float:
        page._render_sig = None
        t0 = time.perf_counter()
        page._render_now()
        t1 = time.perf_counter()
        pump(app, 0.25)
        t2 = time.perf_counter()
        print(f"  {tag:26s} render {1000*(t1-t0):8.0f} ms | 泵稳 {1000*(t2-t1):7.0f} ms "
              f"| 行数 {len(page._rows)}")
        return (t2 - t0) * 1000.0

    print("=== A 现状（每次 inner 变高都刷 scrollregion）")
    run("A 现状")

    print("\n=== B 构建期间屏蔽 region/width 刷新")
    orig_region, orig_width = sf._flush_region, sf._flush_width
    sf._flush_region = lambda: None
    sf._flush_width = lambda: None
    try:
        run("B 屏蔽刷新")
        # 结束后补一次真正的刷新
        t0 = time.perf_counter()
        orig_region()
        orig_width()
        app.update_idletasks()
        app.update()
        print(f"  补一次刷新 {(time.perf_counter()-t0)*1000:.0f} ms  "
              f"region={sf._canvas.cget('scrollregion')}")
    finally:
        sf._flush_region, sf._flush_width = orig_region, orig_width

    print("\n=== C 再跑一次 A 确认可复现")
    run("C 现状复测")

    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
