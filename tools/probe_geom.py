"""量一下窗口/容器/页面的实际尺寸，确认「1858x1402」这种翻倍值从哪来。"""
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


def dump(app, tag):
    print(f"\n--- {tag}")
    print(f"  screen: {app.winfo_screenwidth()}x{app.winfo_screenheight()}")
    print(f"  tk scaling: {app.tk.call('tk', 'scaling')}")
    print(f"  app: {app.winfo_width()}x{app.winfo_height()} "
          f"rootx={app.winfo_rootx()} rooty={app.winfo_rooty()} "
          f"geom={app.winfo_geometry()}")
    cont = getattr(app, "_container", None)
    if cont is not None:
        print(f"  container: {cont.winfo_width()}x{cont.winfo_height()} "
              f"rootx={cont.winfo_rootx()} rooty={cont.winfo_rooty()} "
              f"mgr={cont.winfo_manager()}")
    for key, page in app._pages.items():
        try:
            print(f"  page[{key}]: {page.winfo_width()}x{page.winfo_height()} "
                  f"mgr={page.winfo_manager()!r} place={page.place_info() or '无'}")
        except tk.TclError:
            print(f"  page[{key}]: 已销毁")


def main() -> int:
    from mclite.ui.app import App

    app = App()
    print("== 刚创建")
    settle(app, 0.5)
    dump(app, "刚创建后")

    print("\n== create_pages")
    app.create_pages()
    settle(app, 0.8)
    dump(app, "create_pages 后")

    print("\n== show_page(settings)")
    app.show_page("home")
    settle(app, 0.5)
    app.show_page("settings")
    settle(app, 0.8)
    dump(app, "show_page 后")

    print("\n== 切主题")
    app._pages["settings"]._set_theme("dark")
    settle(app, 1.6)
    dump(app, "切主题后")

    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
