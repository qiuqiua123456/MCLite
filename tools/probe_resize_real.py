"""量「版本列表已渲染满」时，一次窗口拉伸到页面真正重排要多少时间。

之前的 probe_resize_loaded 量出 0.0 ms 是假数字：页面被 _place_page 固定成
绝对尺寸，窗口宽度变了页面也不动，而防抖 70ms 没到就量完了，所以什么都没测到。

这里改成：改窗口宽度后一直泵到页面宽度真的变了为止，同时记录每帧布局耗时。
"""
from __future__ import annotations

import sys
import time
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
            out.append(VersionSummary(f"1.{21 - i % 5}.{i % 4}", "release", "",
                                      "2024-01-01T00:00:00+00:00"))
        elif i % 3 == 1:
            out.append(VersionSummary(f"24w{14 - i % 20:02d}a", "snapshot", "",
                                      "2024-01-01T00:00:00+00:00"))
        else:
            out.append(VersionSummary(f"1.{21 - i % 5}-pre{i % 9 + 1}", "snapshot", "",
                                      "2024-01-01T00:00:00+00:00"))
    return out


def count_widgets(w) -> int:
    try:
        return 1 + sum(count_widgets(c) for c in w.winfo_children())
    except Exception:                              # noqa: BLE001
        return 0


def resize_once(app, page, width: int) -> tuple[float, float]:
    """改宽度 → 泵到页面跟上 → 返回 (总耗时 ms, 单帧布局最慢 ms)。"""
    want = width - app._side.winfo_width() - 2
    app.geometry(f"{width}x724")
    t0 = time.perf_counter()
    app.update_idletasks()
    app.update()
    worst = 0.0
    deadline = t0 + 8.0
    while time.perf_counter() < deadline:
        f0 = time.perf_counter()
        app.update_idletasks()
        worst = max(worst, (time.perf_counter() - f0) * 1000.0)
        app.update()
        if abs(page.winfo_width() - app._container.winfo_width()) <= 2:
            break
        time.sleep(0.005)
    return (time.perf_counter() - t0) * 1000.0, worst


def main() -> int:
    from mclite.ui.app import App

    app = App()
    app.create_pages()
    pump(app, 0.6)
    app.show_page("install")
    pump(app, 0.5)
    page = app._pages["install"]
    page._loading = False

    print("=== 空列表对照")
    print("  控件数:", count_widgets(page))
    for w in (1000, 1240, 1100):
        total, worst = resize_once(app, page, w)
        print(f"  宽 {w}: 对齐 {total:6.0f} ms，单帧布局最慢 {worst:6.1f} ms")

    print("\n=== 加载 920 条清单（真实场景）")
    page._all = big_manifest(920)
    page._filter = None
    page._family = "全部版本"
    page._render_sig = None
    t0 = time.perf_counter()
    page._render_now()
    print(f"  渲染耗 {(time.perf_counter()-t0)*1000:.0f} ms，行数 {len(page._rows)}")
    pump(app, 1.0)
    print("  控件数:", count_widgets(page))
    for w in (1000, 1240, 1100):
        total, worst = resize_once(app, page, w)
        print(f"  宽 {w}: 对齐 {total:6.0f} ms，单帧布局最慢 {worst:6.1f} ms")

    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
