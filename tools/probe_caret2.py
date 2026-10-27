"""确认搜索框左侧那道斜线是不是插入光标：强制 insertwidth=0 再截一张对比。"""

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


def dark_area(path: Path) -> tuple[int, list]:
    from PIL import Image
    im = Image.open(path).convert("RGB")
    w, h = im.size
    hits = []
    for x in range(200, 420):
        for y in range(120, 200):
            r, g, b = im.getpixel((x, y))
            if r < 120 and g < 120 and b < 120:
                hits.append((x, y))
    return len(hits), hits[:6]


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

    print("ph text =", repr(browser._ph.cget("text")))
    print("ph info  =", browser._ph.place_info())
    print("entry width =", entry.winfo_width(), "x offset of ph =",
          browser._ph.winfo_x(), "y =", browser._ph.winfo_y())

    p1 = grab(app, "_caret_on")
    print("A insertwidth=", entry.cget("insertwidth"), " dark=", dark_area(p1)[0])

    entry.configure(insertwidth=0)
    pump(app, 0.5)
    p2 = grab(app, "_caret_off")
    print("B insertwidth=0        dark=", dark_area(p2)[0], dark_area(p2)[1])

    # 再试：把光标位置设置到文本末尾
    entry.icursor("end")
    pump(app, 0.5)
    p3 = grab(app, "_caret_end")
    print("C icursor end          dark=", dark_area(p3)[0])

    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
