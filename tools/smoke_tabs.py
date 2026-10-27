"""冒烟：构建主窗口 + 三个页面 + 两个内嵌页签，检查关键控件是否都建出来。

不打开可见窗口（withdraw），跑完打印 PASS/FAIL 后退出。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

results: list[tuple[str, bool, str]] = []


def check(name: str, fn):
    try:
        fn()
    except Exception as exc:                          # noqa: BLE001
        results.append((name, False, f"{type(exc).__name__}: {exc}"))
    else:
        results.append((name, True, ""))


def main() -> int:
    from mclite.ui.app import NAV_ITEMS, App

    app = App()
    app.withdraw()
    app.create_pages()
    app.update_idletasks()

    check("pages", lambda: (_ for _ in ()).throw(
        AssertionError(f"页面 = {sorted(app._pages)}"))
        if sorted(app._pages) != ["home", "install", "settings"] else None)

    check("nav", lambda: (_ for _ in ()).throw(
        AssertionError(f"导航 = {[k for k, _t, _i in NAV_ITEMS]}"))
        if len(NAV_ITEMS) != 3 else None)

    home = app._pages["home"]
    check("home tabs", lambda: (_ for _ in ()).throw(
        AssertionError("页签不对")) if home._tabs.get() != "launch" else None)

    def open_mods():
        home.show_tab("mods")
        app.update_idletasks()
        assert home._mods_panel is not None, "mods_panel 没建出来"
        assert home._tab_mods.winfo_manager(), "mods 页签没 pack 上"

    check("mods tab", open_mods)

    def open_account():
        home.show_tab("account")
        app.update_idletasks()
        assert home._accounts_panel is not None, "accounts_panel 没建出来"
        assert home._tab_account.winfo_manager(), "account 页签没 pack 上"
        assert not home._tab_mods.winfo_manager(), "切到 account 后 mods 还在"

    check("account tab", open_account)

    def back_launch():
        home.show_tab("launch")
        app.update_idletasks()
        assert home._tab_launch.winfo_manager(), "launch 页签没 pack 上"

    check("back to launch", back_launch)

    def log_toggle():
        assert home._log_open is True, "日志默认应为展开"
        home._toggle_log()
        app.update_idletasks()
        assert not home._log_body.winfo_manager(), "折叠后日志体还 pack 着"
        home._toggle_log()
        app.update_idletasks()
        assert home._log_body.winfo_manager(), "再展开后日志体没 pack 回来"

    check("log collapse", log_toggle)

    install = app._pages["install"]
    check("install tabs", lambda: (_ for _ in ()).throw(
        AssertionError(f"下载页签 = {install._tabs.get()}"))
        if install._tabs.get() != "version" else None)

    def open_browser():
        install.open_browser("shader")
        app.update_idletasks()
        assert install._browser is not None, "浏览器没建出来"
        assert install._tab_browser.winfo_manager(), "浏览器页签没 pack 上"
        assert install._browser._ptype == "shader", f"类型 = {install._browser._ptype}"

    check("download browser", open_browser)

    def switch_page_mods_gone():
        app.show_page("install")
        app.update_idletasks()
        assert app._current == "install"

    check("show_page install", switch_page_mods_gone)

    app.destroy()

    ok = all(r[1] for r in results)
    for name, good, err in results:
        print(f"{'PASS' if good else 'FAIL'}  {name}" + (f"  -> {err}" if err else ""))
    print("ALL PASS" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
