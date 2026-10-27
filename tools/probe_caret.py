"""定位搜索框左侧那道黑色小竖线：是插入光标还是别的东西。"""

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


def grab(app, name: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.png"
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_exe import capture_window            # noqa: PLC0415
    capture_window(app.winfo_id()).save(path)
    return path


def darkest_cols(path: Path, x0: int, x1: int, y0: int, y1: int) -> list:
    from PIL import Image
    im = Image.open(path).convert("RGB")
    out = []
    for x in range(x0, x1):
        dark = 0
        for y in range(y0, y1):
            r, g, b = im.getpixel((x, y))
            if r < 120 and g < 120 and b < 120:
                dark += 1
        if dark:
            out.append((x, dark))
    return out


def main() -> int:
    from mclite.ui.app import App

    app = App()
    app.create_pages()
    pump(app, 0.4)
    app.show_page("install")
    pump(app, 3.0)
    page = app._pages["install"]
    page.open_browser("mod")
    pump(app, 1.0)

    browser = page._browser
    entry = browser._entry
    print("insertwidth =", entry.cget("insertwidth"))
    print("insertontime =", entry.cget("insertontime"))
    print("focus =", entry.focus_get())
    print("entry rootx =", entry.winfo_rootx(), "rooty =", entry.winfo_rooty())

    p1 = grab(app, "_probe_before")
    print("dark before:", darkest_cols(p1, 260, 300, 145, 175))

    # 试 1：把光标闪烁关掉
    entry.configure(insertontime=0, insertofftime=0)
    pump(app, 0.6)
    p2 = grab(app, "_probe_nocaret")
    print("dark with insertontime=0:", darkest_cols(p2, 260, 300, 145, 175))

    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
