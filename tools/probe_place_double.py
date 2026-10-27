"""确认 2 倍尺寸的机制：place() 先给 relwidth=1，后来 place_configure(width=...)
时 Tk 把「相对尺寸 + 绝对尺寸」相加 → 页面变成两倍大。

这条路径就是用户说的「切主题后设置页卡死」：App 刚创建、容器还没实现（1x1）时
show_page 会走 relwidth=1 分支；之后 _flush_page_size 用 place_configure(width=w)
对齐，结果页面 = 929(相对) + 929(绝对) = 1858，右半屏的控件全跑到窗口外面。
"""
from __future__ import annotations

import sys
import time
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def settle(app, sec=1.0):
    end = time.time() + sec
    while time.time() < end:
        app.update()
        time.sleep(0.02)


def main() -> int:
    from mclite.ui.app import App

    # 关键：先不 pump，模拟真实启动（App() 之后立刻有代码去 show_page）
    app = App()
    print("App 创建后（未 pump）container:",
          app._container.winfo_width(), app._container.winfo_height())

    app.create_pages()
    print("create_pages 后（未 pump）container:",
          app._container.winfo_width(), app._container.winfo_height())

    app.show_page("home")
    ps = app._pages["home"]
    print("\nshow_page(home) 未 pump:")
    print("  place_info:", ps.place_info())

    settle(app, 1.2)
    print("\npump 之后:")
    print("  container:", app._container.winfo_width(), app._container.winfo_height())
    print("  home 页:", ps.winfo_width(), ps.winfo_height())
    print("  place_info:", ps.place_info())

    # 换成 settings 也是同样路径
    app.show_page("settings")
    settle(app, 1.0)
    ps2 = app._pages["settings"]
    print("\nshow_page(settings) 后:")
    print("  settings 页:", ps2.winfo_width(), ps2.winfo_height())
    print("  place_info:", ps2.place_info())

    ratio = ps2.winfo_width() / max(1, app._container.winfo_width())
    print(f"\n  宽度比 = {ratio:.2f}")
    if ratio > 1.5:
        print("  >>> 复现了！页面比容器宽一倍")
    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
