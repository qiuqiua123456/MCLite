"""程序入口。"""

from __future__ import annotations

import sys


def _ensure_sys_path() -> None:
    """PyInstaller 单文件模式下保证包能被导入。"""
    if getattr(sys, "frozen", False):
        import os
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        if base not in sys.path:
            sys.path.insert(0, base)


def _start_page() -> str:
    """支持 `MCLite.exe --page install` 直接打开某页（截图/排查用）。

    ``mods`` 不再是独立页面，而是开始页里的一个页签，这里保留入口做兼容。
    """
    import os
    page = os.environ.get("MCLITE_START_PAGE", "")
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--page" and i + 1 < len(args):
            page = args[i + 1]
        elif a.startswith("--page="):
            page = a.split("=", 1)[1]
    return page if page in ("home", "install", "mods", "settings") else "home"


def _selftest(app) -> bool:
    """`MCLITE_SELFTEST=<文件>` 时把运行期状态写成 JSON 就退出（排查打包问题用）。"""
    import json
    import os
    target = os.environ.get("MCLITE_SELFTEST", "")
    if not target:
        return False
    from mclite import __version__

    info = {
        "version": __version__,
        "frozen": bool(getattr(sys, "frozen", False)),
        "dnd": bool(getattr(app, "_dnd_ok", False)),
        "pages": sorted(getattr(app, "_pages", {}).keys()),
    }
    try:
        with open(target, "w", encoding="utf-8") as fh:
            json.dump(info, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass
    app.destroy()
    return True


def main() -> int:
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)     # 高 DPI 清晰
        except Exception:                                       # noqa: BLE001
            pass

    _ensure_sys_path()
    start = _start_page()

    from mclite.ui.app import App

    app = App()
    app.create_pages()

    if _selftest(app):
        return 0

    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.show_page("home" if start == "mods" else start)
    if start == "mods":
        home = app._pages.get("home")
        if home is not None and hasattr(home, "show_tab"):
            app.after(300, lambda: home.show_tab("mods"))
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
