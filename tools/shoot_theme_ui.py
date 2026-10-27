"""滚到设置页「界面」区块，核对主题按钮的选中态在亮色下是否还有暗块。"""

from __future__ import annotations

import ctypes
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:                                  # noqa: BLE001
        pass

OUT = Path(__file__).resolve().parent.parent / "shots"


def pump(app, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.update_idletasks()
        app.update()
        time.sleep(0.02)


def grab(app, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.png"
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from test_exe import capture_window            # noqa: PLC0415
        img = capture_window(app.winfo_id())
    except Exception:                                  # noqa: BLE001
        from PIL import ImageGrab                      # noqa: PLC0415
        x, y = app.winfo_rootx(), app.winfo_rooty()
        w, h = app.winfo_width(), app.winfo_height()
        img = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
    img.save(path)
    print(f"saved -> {path}")


def find_scroll(widget):
    """递归找出页面里的 ScrollFrame（设置页把它存成局部变量，没有属性）。"""
    from mclite.ui.theme import ScrollFrame
    for child in widget.winfo_children():
        if isinstance(child, ScrollFrame):
            return child
        found = find_scroll(child)
        if found is not None:
            return found
    return None


def scroll_to_theme(app) -> None:
    page = app._pages["settings"]
    scroll = find_scroll(page)
    if scroll is None:
        print("找不到 ScrollFrame，跳过滚动")
        return
    canvas = scroll._canvas
    canvas.update_idletasks()
    total = canvas.bbox("all")
    if not total:
        return
    # 「界面」区块在设置页偏下，滚到 65% 左右就露出来了
    canvas.yview_moveto(0.62)
    app.update_idletasks()


def main() -> int:
    theme = sys.argv[1] if len(sys.argv) > 1 else "light"
    from mclite.ui.app import App

    app = App()
    app.create_pages()
    pump(app, 0.4)
    app.apply_theme(theme)
    pump(app, 1.0)
    app.show_page("settings")
    pump(app, 1.0)
    scroll_to_theme(app)
    pump(app, 0.6)
    grab(app, f"themeui_{theme}")

    # 顺便把每个主题按钮的 kind 与配色打出来，便于核对
    page = app._pages["settings"]
    btns = getattr(page, "_theme_btns", {})
    for key, btn in btns.items():
        try:
            fill, fg, outline = btn._colors()
        except Exception:                              # noqa: BLE001
            fill = fg = outline = "?"
        mark = "*" if key == theme else " "
        print(f"{mark} {key:<7} kind={btn.kind:<12} fill={fill} fg={fg}")

    app.apply_theme("pcl")
    pump(app, 0.5)
    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
