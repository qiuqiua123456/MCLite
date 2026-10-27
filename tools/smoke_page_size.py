"""回归测试：页面尺寸不能被 place 的相对+绝对组合翻倍。

历史 bug（用户 m08790 反馈「切换配色后设置界面卡死，只有重新切换回设置才
恢复」）：启动早期容器还没实现（1x1）时 show_page 走 place(relwidth=1)，
之后 _flush_page_size 用 place_configure(width=929) 对齐，Tk 把两者**相加**，
页面变成 1858 宽 —— 正好两倍，右半边的控件（包括「保存设置」按钮）被推到
窗口外面，点不到，看起来就是卡死。切走再切回时重新 place 清掉了 relwidth，
所以「切回来就好了」。

这个脚本覆盖：
1. 每种页面进入时的尺寸 = 容器尺寸（不翻倍）；
2. 换主题重建后仍然相等；
3. 拉伸窗口后仍然相等（走 _flush_page_size）；
4. place_info 里 relwidth/relheight 必须为空；
5. 页面上真实坐标的命中测试落在该页面内。
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


def settle(app, sec=0.8):
    end = time.time() + sec
    while time.time() < end:
        try:
            app.update()
        except tk.TclError:
            return
        time.sleep(0.02)


def ancestors(widget):
    out, node = [], widget
    while node is not None:
        out.append(node)
        node = getattr(node, "master", None)
    return out


def size_matches(app, key):
    page = app._pages[key]
    cw, ch = app._container.winfo_width(), app._container.winfo_height()
    pw, ph = page.winfo_width(), page.winfo_height()
    return (cw, ch), (pw, ph)


def main() -> int:
    from mclite.ui.app import App

    # ---- 关键：在容器还没实现尺寸时就去 show_page，复现启动早期的时序
    app = App()
    app.create_pages()
    app.show_page("home")
    settle(app, 1.2)

    print("=== 启动早期进入 home 页（容器当时还是 1x1）")
    (cw, ch), (pw, ph) = size_matches(app, "home")
    print(f"  容器 {cw}x{ch} / 页面 {pw}x{ph}")
    check(abs(pw - cw) <= 2 and abs(ph - ch) <= 2,
          f"home 页尺寸不翻倍（页面 {pw}x{ph} vs 容器 {cw}x{ch}）")
    info = app._pages["home"].place_info()
    check(not info.get("relwidth") and not info.get("relheight"),
          f"home 页 place 里没有残留 relwidth/relheight（{info.get('relwidth')!r}/{info.get('relheight')!r}）")

    # ---- 逐页检查
    for key in ("install", "settings", "home"):
        app.show_page(key)
        settle(app, 0.9)
        (cw, ch), (pw, ph) = size_matches(app, key)
        ratio = pw / max(1, cw)
        print(f"  {key}: 容器 {cw}x{ch} / 页面 {pw}x{ph} (比 {ratio:.2f})")
        check(abs(pw - cw) <= 2 and abs(ph - ch) <= 2,
              f"{key} 页尺寸等于容器（{pw}x{ph} vs {cw}x{ch}）")
        info = app._pages[key].place_info()
        check(not info.get("relwidth") and not info.get("relheight"),
              f"{key} 页 place 里没有残留相对尺寸")

    # ---- 换主题重建后再查（用户报的触发场景）
    print("\n=== 切主题（用户在设置页点主题按钮）")
    app.show_page("settings")
    settle(app, 0.7)
    for name in ("dark", "light", "pcl"):
        app._pages["settings"]._set_theme(name)
        settle(app, 1.6)
        ps = app._pages["settings"]
        (cw, ch), (pw, ph) = size_matches(app, "settings")
        ratio = pw / max(1, cw)
        print(f"  切到 {name}: 容器 {cw}x{ch} / 页面 {pw}x{ph} (比 {ratio:.2f})")
        check(abs(pw - cw) <= 2 and abs(ph - ch) <= 2,
              f"切到 {name} 后设置页尺寸不翻倍（{pw}x{ph} vs {cw}x{ch}）")
        check(app._current == "settings", f"切到 {name} 后仍在设置页")
        # 命中测试：页面中心点应该是设置页的后代
        #
        # ⚠ winfo_containing 走的是 Win32 WindowFromPoint —— 谁的窗口在最上层就
        # 命中谁。控制台/浏览器盖在应用上面时会返回 None，跟页面尺寸无关。所以
        # 查之前先把窗口提到最前（跟 shot_theme_fix.py 截图时一样的做法）。
        try:
            app.deiconify()
            app.lift()
            app.attributes("-topmost", True)
            settle(app, 0.25)
            node = app.winfo_containing(ps.winfo_rootx() + pw // 2,
                                        ps.winfo_rooty() + ph // 2)
            app.attributes("-topmost", False)
        except tk.TclError:
            node = None
        inside = node is not None and any(a is ps for a in ancestors(node))
        check(inside, f"切到 {name} 后页面中心的点击落在设置页上（命中 {node}）")

    # ---- 拉伸窗口（走 _flush_page_size 的绝对尺寸路径）
    print("\n=== 拉伸窗口后")
    for w, h in ((1100, 700), (1400, 820), (1160, 724)):
        app.geometry(f"{w}x{h}")
        settle(app, 0.9)
        ps = app._pages["settings"]
        (cw, ch), (pw, ph) = size_matches(app, "settings")
        print(f"  窗口 {w}x{h}: 容器 {cw}x{ch} / 页面 {pw}x{ph}")
        check(abs(pw - cw) <= 2 and abs(ph - ch) <= 2,
              f"窗口 {w}x{h} 后设置页尺寸跟随容器（{pw}x{ph} vs {cw}x{ch}）")
        info = ps.place_info()
        check(not info.get("relwidth") and not info.get("relheight"),
              f"窗口 {w}x{h} 后 place 里没有残留相对尺寸")

    app.destroy()
    print()
    print(f"FAIL {len(FAIL)} 项")
    for f in FAIL:
        print("  - " + f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
