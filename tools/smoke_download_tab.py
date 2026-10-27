"""验证「模组」页签里的下载按钮能跳到下载页对应页签。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    from mclite.ui.app import App

    app = App()
    app.withdraw()
    app.create_pages()
    app.update_idletasks()

    home = app._pages["home"]
    install = app._pages["install"]

    ok = True

    for kind, expect in (("mods", "mod"), ("resourcepacks", "resourcepack"),
                         ("shaderpacks", "shader"), ("modpacks", "modpack")):
        app.show_page("home")
        home.show_tab("mods")
        app.update_idletasks()
        home._open_download_tab(kind)
        app.update_idletasks()
        got_page = app._current
        got_tab = install._tabs.get()
        browser_type = install._browser._ptype if install._browser else None
        good = (got_page == "install" and got_tab == expect
                and browser_type == expect)
        ok = ok and good
        print(f"{'PASS' if good else 'FAIL'}  {kind} -> page={got_page} "
              f"tab={got_tab} browser={browser_type}")

    # datapacks 不支持在线下载，应提示而不跳转
    app.show_page("home")
    home.show_tab("mods")
    app.update_idletasks()
    before = app._current
    home._open_download_tab("datapacks")
    app.update_idletasks()
    good = app._current == before
    ok = ok and good
    print(f"{'PASS' if good else 'FAIL'}  datapacks 不跳转 (page={app._current})")

    app.destroy()
    print("ALL PASS" if ok else "HAS FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
