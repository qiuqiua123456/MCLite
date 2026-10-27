"""选渲染上限：不同 budget 下「拉伸到页面跟上」要多久。

版本行每行约 6 个控件（SelectableRow + 竖条 + box + 2 个 Label + 绑定），
400 行就是 2400+ 控件；窗口一改宽，Tk 要把这 2400 个全重排一遍。
"""
from __future__ import annotations

import statistics
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
    """造 920 条**不重名**的版本，和真实清单同量级。"""
    out = []
    for i in range(n):
        if i % 3 == 0:
            out.append(VersionSummary(f"1.{40 - i // 30}.{i % 30}", "release", "",
                                      "2024-01-01T00:00:00+00:00"))
        elif i % 3 == 1:
            out.append(VersionSummary(f"24w{i % 50:02d}a", "snapshot", "",
                                      "2024-01-01T00:00:00+00:00"))
        else:
            out.append(VersionSummary(f"1.{40 - i // 30}-pre{i % 30 + 1}", "snapshot", "",
                                      "2024-01-01T00:00:00+00:00"))
    return out


def count_widgets(w) -> int:
    try:
        return 1 + sum(count_widgets(c) for c in w.winfo_children())
    except Exception:                              # noqa: BLE001
        return 0


def resize_once(app, page, width: int) -> float:
    app.geometry(f"{width}x724")
    t0 = time.perf_counter()
    app.update_idletasks()
    app.update()
    deadline = t0 + 15.0
    while time.perf_counter() < deadline:
        app.update_idletasks()
        app.update()
        if abs(page.winfo_width() - app._container.winfo_width()) <= 2:
            break
        time.sleep(0.005)
    return (time.perf_counter() - t0) * 1000.0


def main() -> int:
    import mclite.ui.page_install as pi
    from mclite.ui.app import App

    app = App()
    app.create_pages()
    pump(app, 0.6)
    app.show_page("install")
    pump(app, 0.5)
    page = app._pages["install"]
    page._loading = False
    page._all = big_manifest(920)

    # 让 budget 可通过 page 属性调
    orig = pi.VersionSummary

    for budget in (400, 250, 160, 120, 80, 60):
        page._budget = budget
        page._filter = None
        page._family = "全部版本"
        page._render_sig = None
        t0 = time.perf_counter()
        page._render_now()
        render_ms = (time.perf_counter() - t0) * 1000.0
        pump(app, 0.8)
        widgets = count_widgets(page)
        times = [resize_once(app, page, w) for w in (1000, 1240, 1100)]
        print(f"budget={budget:4d}  渲染 {render_ms:6.0f} ms | 控件 {widgets:5d} "
              f"| 拉伸对齐 中位 {statistics.median(times):6.0f} ms "
              f"最慢 {max(times):6.0f} ms")

    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
