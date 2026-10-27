"""深挖「切换配色后设置页卡死」。

上一个复现脚本只查了控件是否存在，结果全绿 —— 说明状态没坏。那「卡死」得是
别的东西：要么主循环被榨干（一次 update 变得极慢），要么点击/滚轮事件到不了
设置页，要么界面根本不重绘。

这个脚本从四个角度探：
1. 每次 update 的耗时（主循环卡不卡）；
2. 真实鼠标事件能不能打到设置页的按钮上（event_generate 定位到控件坐标）；
3. 滚轮还能不能滚动设置页（ScrollFrame 的 bind_all 有没有被重建打断）；
4. 连着切好几次主题，看是否越来越慢 / after 任务堆积。
"""
from __future__ import annotations

import sys
import time
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FAIL: list[str] = []


def check(cond, msg):
    if not cond:
        FAIL.append(msg)
    print(("  ok   " if cond else "  FAIL ") + msg)


def settle(app, sec=1.0):
    end = time.time() + sec
    while time.time() < end:
        app.update()
        time.sleep(0.02)


def frame_cost(app, n=20):
    """测 n 次 update 的中位耗时（ms）。"""
    costs = []
    for _ in range(n):
        t0 = time.perf_counter()
        app.update_idletasks()
        app.update()
        costs.append((time.perf_counter() - t0) * 1000)
    costs.sort()
    return costs[len(costs) // 2]


def click_widget(app, widget):
    """在控件中心生成一次真实的 Button-1 按下/抬起。"""
    settle(app, 0.15)
    try:
        x = widget.winfo_width() // 2
        y = widget.winfo_height() // 2
    except tk.TclError:
        return False
    try:
        widget.event_generate("<Button-1>", x=x, y=y)
        widget.event_generate("<ButtonRelease-1>", x=x, y=y)
    except tk.TclError:
        return False
    settle(app, 0.3)
    return True


def wheel_target(app):
    """当前 <MouseWheel> 绑在谁身上（ScrollFrame 用 bind_all 绑的）。"""
    try:
        return app.bind_all("<MouseWheel>")
    except tk.TclError:
        return ""


def main() -> int:
    from mclite.ui.app import App

    app = App()
    app.create_pages()
    app.show_page("settings")
    settle(app, 1.5)

    base = frame_cost(app)
    print(f"=== 切主题前：单帧 {base:.1f} ms，滚轮绑定 {wheel_target(app)!r}")

    # ---- 连切三次主题，每次测帧耗时和可用性
    for name in ("dark", "pcl", "light"):
        print(f"\n=== 切到 {name}")
        ps = app._pages["settings"]
        try:
            ps._set_theme(name)
        except Exception as exc:                        # noqa: BLE001
            print("  _set_theme 抛异常:", exc)
        settle(app, 1.8)

        ps = app._pages.get("settings")
        cost = frame_cost(app)
        print(f"  切完单帧 {cost:.1f} ms，滚轮绑定 {wheel_target(app)!r}")
        check(cost < base * 3 + 20, f"切到 {name} 后主循环没变慢（{cost:.1f} vs {base:.1f} ms）")

        # ---- 真实点击「浏览」旁边的按钮？用「保存设置」更安全：走 save_all
        hit = {"n": 0}
        orig = ps.save_all
        ps.save_all = lambda: hit.__setitem__("n", hit["n"] + 1)
        # 「保存设置」按钮是 head 里唯一一个 FlatButton
        btn = None
        for child in ps.winfo_children():
            for sub in child.winfo_children():
                if sub.__class__.__name__ == "FlatButton":
                    btn = sub
        ok = click_widget(app, btn) if btn is not None else False
        ps.save_all = orig
        check(ok and hit["n"] == 1,
              f"切到 {name} 后点「保存设置」能触发（btn={btn is not None}, hits={hit['n']}）")

        # ---- 滚轮：看 ScrollFrame 的 canvas 能否滚动
        sf = None
        for child in ps.winfo_children():
            for sub in child.winfo_children():
                if sub.__class__.__name__ == "ScrollFrame":
                    sf = sub
        if sf is not None:
            before = sf._canvas.yview()[0]
            try:
                sf._canvas.event_generate("<MouseWheel>", delta=-120)
            except tk.TclError:
                pass
            settle(app, 0.3)
            after = sf._canvas.yview()[0]
            # 内容比视口高才谈得上滚动
            try:
                scrollable = sf._canvas.bbox("all")[3] > sf._canvas.winfo_height()
            except (tk.TclError, TypeError):
                scrollable = False
            print(f"  滚轮: yview {before:.3f} -> {after:.3f}（可滚动={scrollable}）")

        # ---- 当前页 & 控件树
        print(f"  当前页 {app._current}，设置页子控件 "
              f"{len(ps.winfo_children())} 个")

    # ---- 切走后切回，看是不是真的「恢复」了什么
    print("\n=== 切到 home 再切回 settings")
    app.show_page("home")
    settle(app, 0.8)
    app.show_page("settings")
    settle(app, 0.8)
    cost = frame_cost(app)
    print(f"  切回后单帧 {cost:.1f} ms")
    check(cost < base * 3 + 20, f"切回设置页后主循环正常（{cost:.1f} vs {base:.1f} ms）")

    # ---- after 任务堆积检查
    try:
        jobs = len(app.tk.call("after", "info"))
    except tk.TclError:
        jobs = -1
    print(f"\n  待执行的 after 任务数: {jobs}")

    app.destroy()
    print()
    print(f"FAIL {len(FAIL)} 项")
    for f in FAIL:
        print("  - " + f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
