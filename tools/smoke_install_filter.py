"""回归：下载页版本列表的「大版本分组 + 下拉筛选 + 切换耗时」。

用户反馈：①列表要按大版本号分类；②切换筛选「很卡」；③版本输入框改成下拉。
这里不联网，直接塞一份假 manifest 进页面，然后：
- 校验 version_family 的分组结果；
- 校验下拉里出现的大版本、分组标题行数；
- 量一次「切筛选 + 切下拉」的耗时（预算 120 ms，含 after(1) 空闲渲染）。
"""

from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BUDGET_MS = 120.0


def pump(app, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.update_idletasks()
        app.update()
        time.sleep(0.01)


def fake_versions():
    from mclite.versionmeta import VersionSummary

    ids = []
    for major, minor, patch in [(1, 21, 4), (1, 21, 1), (1, 21, 0), (1, 20, 6),
                                (1, 20, 1), (1, 19, 4), (1, 18, 2), (1, 16, 5),
                                (1, 12, 2), (1, 8, 9), (1, 7, 10)]:
        vid = f"{major}.{minor}" + (f".{patch}" if patch else "")
        ids.append(VersionSummary(vid, "release", f"http://x/{vid}.json",
                                  "2024-01-01T00:00:00+00:00"))
    for snap in ("24w14a", "23w31a", "1.20-pre1"):
        ids.append(VersionSummary(snap, "snapshot", f"http://x/{snap}.json",
                                  "2023-04-01T00:00:00+00:00"))
    for old in ("b1.7.3", "a1.2.6"):
        ids.append(VersionSummary(old, "old_beta", f"http://x/{old}.json",
                                  "2011-01-01T00:00:00+00:00"))
    return ids


def main() -> int:
    from mclite.ui.app import App
    from mclite.ui.page_install import ALL_FAMILY, _family_key, version_family

    fails = 0

    # ---- 纯函数：分组规则
    from mclite.versionmeta import VersionSummary
    cases = [
        (VersionSummary("1.21.4", "release", ""), "1.21"),
        (VersionSummary("1.21", "release", ""), "1.21"),
        (VersionSummary("1.7.10", "release", ""), "1.7"),
        (VersionSummary("24w14a", "snapshot", ""), "快照"),
        (VersionSummary("1.20-pre1", "snapshot", ""), "快照"),
        (VersionSummary("b1.7.3", "old_beta", ""), "远古版本"),
        (VersionSummary("a1.2.6", "old_alpha", ""), "远古版本"),
    ]
    for v, want in cases:
        got = version_family(v)
        ok = got == want
        fails += 0 if ok else 1
        print(f"{'PASS' if ok else 'FAIL'}  family({v.id:12s}) = {got:8s} 期望 {want}")

    order = sorted(["1.21", "1.20", "快照", "远古版本", "其他版本", "1.7"], key=_family_key)
    ok = order[:2] == ["1.21", "1.20"] and order[0] == "1.21"
    fails += 0 if ok else 1
    print(f"{'PASS' if ok else 'FAIL'}  分组排序 = {order}")

    # ---- 界面：塞假清单
    app = App()
    app.create_pages()
    page = app._pages["install"]
    # 页面 build() 里排了 after(200, self.load_manifest)，会去拉线上 920 条真清单
    # 并把这里的假清单覆盖掉（列表从 16 行变 60 行、1.20 组里多出 1.20.2–1.20.5）。
    # ⚠ 替换 page.load_manifest 拦不住它：after() 在调度那一刻就把绑定方法对象抓走了，
    # 之后再改属性对已排队的回调无效。这里能拦住的是页面里排的「下一次」加载。
    page.load_manifest = lambda *a, **k: None
    pump(app, 0.6)
    app.show_page("install")
    pump(app, 0.5)

    page._loading = False
    page._on_manifest(fake_versions())
    # 填完假清单就把入口焊死：线上真清单无论什么时候晚到都不会再覆盖它。
    # 不焊这一下，本测试的结果取决于网络延迟（时快时慢 → 有时 16 行、有时 60 行）。
    page._on_manifest = lambda *a, **k: None
    pump(app, 0.4)

    fams = page._families()
    want_first = "1.21"
    ok = fams[0] == ALL_FAMILY and want_first in fams
    fails += 0 if ok else 1
    print(f"{'PASS' if ok else 'FAIL'}  下拉选项 = {fams}")

    heads = [w for w in page._scroll.inner.winfo_children()]
    # 分组标题是 Frame，版本行是 SelectableRow
    n_group = 0
    for w in heads:
        kids = w.winfo_children()
        if len(kids) == 2 and not hasattr(w, "_on_click"):
            n_group += 1
    ok = n_group >= 6
    fails += 0 if ok else 1
    print(f"{'PASS' if ok else 'FAIL'}  分组标题 {n_group} 个（至少 6）")

    # 全部版本下应显示所有 16 条
    page._filter = None
    page._family = ALL_FAMILY
    page._render_sig = None
    page._render_now()
    pump(app, 0.3)
    total_rows = len(page._rows)
    ok = total_rows == 16
    fails += 0 if ok else 1
    print(f"{'PASS' if ok else 'FAIL'}  全部筛选下 {total_rows} 行（期望 16）")

    # ---- 耗时：切筛选 / 切下拉（含 after(1) 渲染 + 一次 update）
    def timed(fn) -> float:
        t0 = time.perf_counter()
        fn()
        app.update_idletasks()
        app.update()
        return (time.perf_counter() - t0) * 1000.0

    samples = []
    for _ in range(5):
        samples.append(timed(lambda: page._set_filter("release")))
        samples.append(timed(lambda: page._set_filter(None)))
    med = statistics.median(samples)
    worst = max(samples)
    ok = med <= BUDGET_MS
    fails += 0 if ok else 1
    print(f"{'PASS' if ok else 'FAIL'}  切换类型筛选 中位 {med:6.1f} ms  最慢 {worst:6.1f} ms")

    samples = []
    for name in ("1.20", "1.21", ALL_FAMILY, "快照", "1.21"):
        samples.append(timed(lambda n=name: page._on_family(n)))
    med = statistics.median(samples)
    worst = max(samples)
    ok = med <= BUDGET_MS
    fails += 0 if ok else 1
    print(f"{'PASS' if ok else 'FAIL'}  切换大版本下拉 中位 {med:6.1f} ms  最慢 {worst:6.1f} ms")

    # 选中「1.20」后，行数应该只有 1.20.x 的
    page._filter = None
    page._family = "1.20"
    page._render_sig = None
    page._render_now()
    pump(app, 0.2)
    ids = sorted(page._rows)
    ok = ids == ["1.20.1", "1.20.6"]
    fails += 0 if ok else 1
    print(f"{'PASS' if ok else 'FAIL'}  选 1.20 后列表 = {ids}")

    app.destroy()
    print()
    print("ALL PASS" if not fails else f"{fails} 项不符")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
