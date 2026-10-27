"""第三次深挖：找出「切主题后设置页卡死」的真正机制。

前两次探针证明：切完主题，设置页控件都活着、几何正常、选中态正确。
所以「卡死」不是状态坏了，最可能是**有一个旧控件盖在新页面上吃掉点击**，
或者页面根本不是被显示的那一个。

这个脚本的杀手锏是 `winfo_containing`：在设置页区域里挑几个屏幕坐标，
问系统「这个点最上层是哪个控件」，然后看它是不是当前设置页的后代。
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


def settle(app, sec=1.2):
    end = time.time() + sec
    while time.time() < end:
        app.update()
        time.sleep(0.02)


def ancestors(widget):
    """从 widget 一路往上，返回控件列表（含自己）。"""
    out = []
    node = widget
    while node is not None:
        out.append(node)
        try:
            parent = node.master
        except (tk.TclError, AttributeError):
            break
        node = parent
    return out


def top_at(x, y):
    try:
        return tk.Misc.winfo_containing(None, x, y) if False else None
    except tk.TclError:
        return None


def probe_points(app, page):
    """在页面区域里取样，看命中的控件是不是这个页面的后代。"""
    app.update()
    x0 = page.winfo_rootx()
    y0 = page.winfo_rooty()
    w = page.winfo_width()
    h = page.winfo_height()
    pts = [(x0 + 40, y0 + 30), (x0 + w // 2, y0 + 40),
           (x0 + 40, y0 + h // 2), (x0 + w // 2, y0 + h // 2),
           (x0 + w - 60, y0 + h - 60)]
    out = []
    for (x, y) in pts:
        try:
            node = app.winfo_containing(x, y)
        except tk.TclError:
            node = None
        inside = False
        if node is not None:
            inside = any(a is page for a in ancestors(node))
        out.append((x - x0, y - y0, str(node), inside))
    return out, (x0, y0, w, h)


def app_children(report):
    pass


def main() -> int:
    from mclite.ui.app import App

    app = App()
    app.create_pages()
    app.show_page("settings")
    settle(app, 1.5)

    print("=== 切主题前 App 直接子控件:",
          [(c.__class__.__name__, c.winfo_manager()) for c in app.winfo_children()])
    ps = app._pages["settings"]
    pts, geom = probe_points(app, ps)
    print("  页面几何(屏幕):", geom)
    for dx, dy, node, inside in pts:
        print(f"   ({dx},{dy}) -> {node}  in_page={inside}")
    check(all(p[3] for p in pts), "切主题前：设置页区域的点击都落在设置页上")

    # ---- 真实点一次主题按钮：先 Enter（hover 置位），再按/抬
    print("\n=== 点击「暗色」主题按钮（带 hover）")
    btn = ps._theme_btns["dark"]
    try:
        btn.event_generate("<Enter>")
        settle(app, 0.1)
        btn.event_generate("<Button-1>")
        btn.event_generate("<ButtonRelease-1>")
    except tk.TclError as exc:
        print("  事件生成失败:", exc)
    settle(app, 2.2)

    print("\n=== 切主题后")
    print("  _current:", app._current)
    print("  App 直接子控件:",
          [(c.__class__.__name__, c.winfo_manager()) for c in app.winfo_children()])
    print("  页面表:", sorted(app._pages))
    ps2 = app._pages.get("settings")
    check(ps2 is not None, "设置页还在页面表里")
    if ps2 is None:
        app.destroy()
        return 1
    check(ps2 is not ps, "设置页确实被重建成了新对象")

    pts2, geom2 = probe_points(app, ps2)
    print("  新页面几何(屏幕):", geom2)
    for dx, dy, node, inside in pts2:
        print(f"   ({dx},{dy}) -> {node}  in_page={inside}")
    check(all(p[3] for p in pts2),
          "切主题后：设置页区域的点击仍落在设置页上（没被旧控件盖住）")

    # ---- 谁盖住了？把命中的控件链打出来
    for dx, dy, node, inside in pts2:
        if not inside and node is not None:
            print(f"   ⚠ 被盖住: ({dx},{dy}) 命中链:")
            try:
                n = app.winfo_containing(geom2[0] + dx, geom2[1] + dy)
                for a in ancestors(n)[:8]:
                    print("      ", a)
            except tk.TclError:
                pass

    # ---- 真实点一次「保存设置」，走 hover 路径
    print("\n=== 点「保存设置」")
    target = None
    for child in ps2.winfo_children():
        for sub in child.winfo_children():
            if sub.__class__.__name__ == "FlatButton" and getattr(sub, "_text", "") == "保存设置":
                target = sub
    if target is None:
        # 递归找
        stack = [ps2]
        while stack and target is None:
            cur = stack.pop()
            for sub in cur.winfo_children():
                if sub.__class__.__name__ == "FlatButton" and getattr(sub, "_text", "") == "保存设置":
                    target = sub
                    break
                stack.append(sub)
    print("  找到按钮:", target)
    hit = {"n": 0}
    if target is not None:
        orig = ps2.save_all
        ps2.save_all = lambda: hit.__setitem__("n", hit["n"] + 1)
        target.event_generate("<Enter>")
        settle(app, 0.1)
        target.event_generate("<Button-1>")
        target.event_generate("<ButtonRelease-1>")
        settle(app, 0.4)
        ps2.save_all = orig
    check(hit["n"] == 1, f"切主题后点「保存设置」能触发（hits={hit['n']}）")

    # ---- 轮播：切走再切回，看几何是否变化（用户的「恢复」办法）
    print("\n=== 切到 home 再回 settings")
    app.show_page("home")
    settle(app, 0.8)
    app.show_page("settings")
    settle(app, 0.8)
    ps3 = app._pages["settings"]
    pts3, geom3 = probe_points(app, ps3)
    print("  页面几何(屏幕):", geom3, " place:", ps3.place_info().get("width"),
          ps3.place_info().get("height"))
    check(all(p[3] for p in pts3), "切走后切回：点击仍落在设置页上")

    app.destroy()
    print()
    print(f"FAIL {len(FAIL)} 项")
    for f in FAIL:
        print("  - " + f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
