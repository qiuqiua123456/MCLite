"""下载页各页签的截图（源码版），核对搜索栏布局。"""

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


def main() -> int:
    prefix = sys.argv[1] if len(sys.argv) > 1 else "dl"
    from mclite.ui.app import App

    app = App()
    app.create_pages()
    pump(app, 0.4)
    app.show_page("install")
    pump(app, 4.0)

    page = app._pages["install"]
    for kind in ("mod", "resourcepack", "shader", "modpack"):
        page.open_browser(kind)
        pump(app, 1.0)
        # 先拍一张「空输入框 + 占位文字」，用来核对占位是否被裁剪在框内
        page._browser._entry_var.set("")
        page._browser._placeholder_visible()
        pump(app, 0.3)
        grab(app, f"{prefix}_{kind}_ph")
        # 打一次搜索，看看结果栏与右栏
        if kind == "mod":
            page._browser._entry_var.set("小地图")
            page._browser.do_search()
            pump(app, 3.0)
        if kind == "modpack":
            page._browser._entry_var.set("优化")
            page._browser.do_search()
            pump(app, 4.0)
        grab(app, f"{prefix}_{kind}")

    # 版本页签
    page._tabs.set("version", fire=True)
    pump(app, 1.0)
    grab(app, f"{prefix}_version")

    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
