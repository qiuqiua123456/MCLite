"""假设：窗口拉伸卡顿的真凶是「版本列表被渲染满 400 行」后的布局开销。
现有 smoke_resize 测的是空列表，所以完全没测到这个场景。

这里手动塞 920 条假版本（和真实清单同量级），等渲染完，再量拉伸单帧。
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
    major, minor, patch = 1, 21, 4
    for i in range(n):
        if i % 3 == 0:
            ident = f"{major}.{minor}.{patch}"
            kind = "release"
            patch -= 1
            if patch < 0:
                patch = 4
                minor -= 1
                if minor < 0:
                    minor = 20
                    major -= 1
        elif i % 3 == 1:
            ident = f"24w{14 - (i % 20):02d}a"
            kind = "snapshot"
        else:
            ident = f"{major}.{minor}-pre{i % 9 + 1}"
            kind = "snapshot"
        out.append(VersionSummary(ident, kind, "", "2024-01-01T00:00:00+00:00"))
    return out


def count_widgets(w) -> int:
    try:
        return 1 + sum(count_widgets(c) for c in w.winfo_children())
    except Exception:                              # noqa: BLE001
        return 0


def measure_resize(app, page, tag: str, widths=(1000, 1240, 1080, 1400, 1160)) -> None:
    samples = []
    for w in widths:
        app.geometry(f"{w}x724")
        app.update()
        t0 = time.perf_counter()
        app.update_idletasks()
        t1 = time.perf_counter()
        app.update()
        t2 = time.perf_counter()
        samples.append((1000 * (t1 - t0), 1000 * (t2 - t1)))
    mid = sorted(s[0] for s in samples)[len(samples) // 2]
    worst = max(s[0] for s in samples)
    mid_draw = sorted(s[1] for s in samples)[len(samples) // 2]
    print(f"  {tag:18s} 布局中位 {mid:7.1f} | 布局最慢 {worst:7.1f} | 重绘中位 {mid_draw:7.1f} ms")


def main() -> int:
    from mclite.ui.app import App

    app = App()
    app.create_pages()
    pump(app, 0.6)

    print("=== 空列表（现有 smoke_resize 的场景）")
    app.show_page("install")
    pump(app, 0.5)
    page = app._pages["install"]
    page._loading = False
    page._all = []
    page._render_sig = None
    page._render_now()
    pump(app, 0.3)
    print("  控件数:", count_widgets(page))
    measure_resize(app, page, "install 空列表")

    print("\n=== 塞 920 条清单（≈ 用户真实场景）")
    page._all = big_manifest(920)
    page._filter = None
    page._family = "全部版本"
    page._render_sig = None
    t0 = time.perf_counter()
    page._render_now()
    pump(app, 0.5)
    print(f"  渲染 920 条耗时 {(time.perf_counter()-t0)*1000:.0f} ms，行数 {len(page._rows)}，"
          f"控件数 {count_widgets(page)}")
    measure_resize(app, page, "install 920 条")

    print("\n=== home 页对照")
    app.show_page("home")
    pump(app, 0.4)
    measure_resize(app, app._pages["home"], "home")

    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
