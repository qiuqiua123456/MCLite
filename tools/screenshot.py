"""离屏截图工具：渲染界面到 PNG，便于在无交互环境下检查 UI。

用法：python tools/screenshot.py [页面名] [输出路径]
"""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:                                  # noqa: BLE001
        pass


def capture(win, out_path: Path) -> bool:
    """用 Win32 PrintWindow 把窗口画到内存 DC，再存 PNG（不受其它窗口遮挡影响）。"""
    win.update_idletasks()
    win.update()
    win.lift()
    win.update()
    import time
    time.sleep(0.5)
    try:
        from test_exe import capture_window          # 同目录，复用 PrintWindow 实现
        img = capture_window(win.winfo_id())
    except Exception:                                # noqa: BLE001
        from PIL import ImageGrab  # type: ignore
        x, y = win.winfo_rootx(), win.winfo_rooty()
        w, h = win.winfo_width(), win.winfo_height()
        img = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
    img.save(out_path)
    return True


def main() -> int:
    page = sys.argv[1] if len(sys.argv) > 1 else "home"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("shots") / f"{page}.png"
    out.parent.mkdir(parents=True, exist_ok=True)

    from mclite.ui.app import App

    app = App()
    app.create_pages()

    app.show_page("home")
    app.update_idletasks()
    app.update()

    # 给异步加载留点时间
    import time
    deadline = time.time() + 6.0
    while time.time() < deadline:
        app.update_idletasks()
        app.update()
        time.sleep(0.05)

    # 「mods」页签现在挂在开始页里，不再是独立页面
    if page == "mods":
        home = app._pages["home"]
        app.show_page("home")
        for _ in range(20):
            app.update_idletasks()
            app.update()
            time.sleep(0.05)
        home.show_tab("mods")
    else:
        app.show_page(page)
    for _ in range(60):
        app.update_idletasks()
        app.update()
        time.sleep(0.05)

    ok = capture(app, out)
    print(f"saved -> {out} ({'ok' if ok else 'failed'})")
    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
