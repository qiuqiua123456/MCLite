"""回归：拉伸窗口时的卡顿（用户反馈「页面拉伸的时候很卡」）。

## 测什么 / 为什么这么测

真实拖边框是「连续很多帧 <Configure>，然后停手」。Tk 的每帧成本分两块：

1. **布局**（`update_idletasks`）：父容器新尺寸 → 重新算所有子控件几何。
   这部分**完全由我们的控件树决定**，是唯一能优化的部分。
2. **重绘**（`update`）：窗口变宽后把像素刷一遍。这块由 Tk/Windows 的窗口
   合成决定，本机实测 34 ms/帧且与本项目的控件结构无关（空窗口也要 4 ms，
   挂一层 Canvas 就要 5 ms）——真实拖动时 OS 会合并 WM_PAINT，压测里这种
   同步重绘是上限值。所以它**只报告、不设预算**，否则这个测试会变成在考
   「这台机器的 GDI 快不快」。

防抖（`App._on_container_configure`，70 ms）保证拖动全程页面不重排，只留
窗口重绘；停手后一次性把页面换成新尺寸。v1.7.3 起拖动期间还会给页面拍一张
像素快照盖上去（`App._ensure_snapshot`），页面本身 place_forget，所以拖动帧
连「重绘真页面」都不用付。

- `BUDGET_MS`  拖动中单帧的**布局**耗时。这是回归线（原 75–97 ms），不是
  性能目标：定得比机器噪声还紧只会得到随机失败。
- `STOP_MS`    松手到页面真正跟上新尺寸的总耗时。它不是纯布局成本，而是
  「70 ms 页面防抖 + 一次整窗重绘 + 一次快照销毁」的和。逐项实测
  （`tools/probe_stop_one.py`，install 页中位）：baseline 281、把 70 ms 防抖
  拿掉 172。`probe_settle_after.py` 后来找到更大的头：**每次单发 <Configure>
  都拍了一张 260 ms 的快照**（`App._ensure_snapshot`）。改成「只有连着第二个
  Configure 才拍」（= 用户真的在拖）之后，install 从 390–400 ms 掉到
  150–190 ms，三页都能稳在 300 ms 以内。
  用户感知的「拖动中画面」另有指标：`smoke_snapshot.py` 逐像素比对 0.00% 差异。
"""

from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 拖动中单帧布局预算。它是回归线，不是性能目标：优化前本机实测 75–97 ms，
# 现在 13–20 ms（差 5 倍），所以 25 ms 已经完全够分辨「有没有退化」。定更紧
# 只是在跟测试机负载较劲——同一份代码连跑三次，中位会从 13.3 飘到 20.4
# （后台在跑别的动西时更明显），那种数字不该判失败。
BUDGET_MS = 25.0
STOP_MS = 300.0
PAGES = ("home", "install", "settings")
WIDTHS = (1000, 1090, 1180, 1270, 1360, 1450, 1360, 1270)


def pump(app, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.update_idletasks()
        app.update()
        time.sleep(0.005)


def settle_once(app, name: str):
    """挪一下窗口，然后一直泵主循环，直到页面宽度真的变成容器宽度。

    返回 (从松手到页面跟上所用毫秒, 该过程中单帧布局最慢毫秒)。
    量「追上那一刻」而不是固定 pump 一段时间——固定 pump 量出来永远等于
    pump 时长，那是个假数字。

    ⚠ 这一轮的绝对耗时主要由**首帧整窗重绘**决定（实测 idle 20 ms、
    update 130–270 ms），而 update 的耗时跟「屏幕上有没有别的窗口压着」
    「DWM 这一拍在不在合成」强相关：同一份代码单跑 250 ms，控制台窗口
    盖在旁边时能到 780 ms。所以调用方取三次中位，别拿单次下结论。
    """
    page = app._pages[name]
    app.geometry("1160x724")
    app.update_idletasks()
    app.update()
    pump(app, 0.30)  # 让上一轮的防抖和重排彻底安静下来

    app.geometry("1290x724")
    t0 = time.perf_counter()
    app.update_idletasks()
    app.update()
    deadline = t0 + 3.0
    worst_layout = 0.0
    while time.perf_counter() < deadline:
        f0 = time.perf_counter()
        app.update_idletasks()
        worst_layout = max(worst_layout, (time.perf_counter() - f0) * 1000.0)
        app.update()
        want = app._container.winfo_width()
        if abs(page.winfo_width() - want) <= 2:
            break
        time.sleep(0.004)
    return (time.perf_counter() - t0) * 1000.0, worst_layout


def main() -> int:
    from mclite.ui.app import App

    app = App()
    # ⚠ 必须掐掉下载页的「拉线上版本清单」（build() 里 after(200, load_manifest)）。
    # 920 条清单一次渲染 ~400 ms，正好会掉进 install 页的测量窗口里，让「松手到
    # 跟上」偶尔跳到 950 ms —— 那是网络到达时机，不是布局性能。掐掉后本机稳定
    # 在 270–380 ms。（同 smoke_install_filter.py 的做法。）
    app.create_pages()
    try:
        app._pages["install"].load_manifest = lambda *a, **k: None
    except (KeyError, AttributeError):
        pass
    pump(app, 0.8)

    # 预热：第一次碰到某页/某宽度会走 Tk 的字体度量与 GDI 路径首次加载，
    # 那一次天然慢 2–3 倍。不预热就取中位，等于让「第一个跑的面板」背锅。
    for name in PAGES:
        app.show_page(name)
        pump(app, 0.4)
        for w in WIDTHS[:3]:
            app.geometry(f"{w}x724")
            app.update_idletasks()
            app.update()
        settle_once(app, name)

    fails = 0
    for name in PAGES:
        app.show_page(name)
        pump(app, 0.5)
        layouts = []
        redraws = []
        for w in WIDTHS:
            app.geometry(f"{w}x724")
            app.update_idletasks()
            app.update()
            t0 = time.perf_counter()
            app.geometry(f"{w + 8}x724")
            app.update_idletasks()
            layouts.append((time.perf_counter() - t0) * 1000.0)
            t1 = time.perf_counter()
            app.update()
            redraws.append((time.perf_counter() - t1) * 1000.0)
            time.sleep(0.01)
        med = statistics.median(layouts)
        worst = max(layouts)
        redraw = statistics.median(redraws)
        # 松手对齐取三次中位：单次结果被「是否有别的窗口压在上面」左右
        # （同一份代码能在 250 与 780 ms 之间跳），一次定生死就是随机失败。
        settles = [settle_once(app, name) for _ in range(3)]
        settle = statistics.median(s[0] for s in settles)
        settle_layout = max(s[1] for s in settles)
        ok = med <= BUDGET_MS and settle <= STOP_MS
        fails += 0 if ok else 1
        print(f"{'PASS' if ok else 'FAIL'}  resize/{name:9s} "
              f"拖动单帧布局 中位 {med:5.1f} 最慢 {worst:5.1f} ms  "
              f"(重绘参考 {redraw:5.1f})  松手对齐 {settle:5.0f} ms "
              f"(其中单帧布局 {settle_layout:4.1f})  "
              f"三次 {[round(s[0]) for s in settles]}")

    app.geometry("1160x724")
    pump(app, 0.3)
    app.destroy()
    print()
    print("ALL PASS" if not fails else f"{fails} 项超预算")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
