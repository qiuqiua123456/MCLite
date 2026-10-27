"""验证「点文字也能切换版本」这个修复是否真的生效。

不靠肉眼：直接给第 2 个版本行里的某个 Label 发 <Button-1>，
然后检查页面当前选中的版本有没有跟着变。
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mclite.ui.app import App  # noqa: E402
from mclite.ui.page_home import HomePage  # noqa: E402


def labels(widget, out=None):
    out = out if out is not None else []
    for child in widget.winfo_children():
        if child.winfo_class() == "Label":
            out.append(child)
        labels(child, out)
    return out


def main() -> int:
    app = App()
    app.register_page("home", HomePage(app._container, app))
    app.show_page("home")
    home = app._pages["home"]

    for _ in range(40):
        app.update()
        if len(home._rows) >= 2:
            break
        app.update_idletasks()
        import time
        time.sleep(0.1)

    rows = list(home._rows.items())
    print("版本行:", [k for k, _ in rows])
    if len(rows) < 2:
        print("版本不足 2 个，跳过")
        app.destroy()
        return 1

    first_vid, first_row = rows[0]
    second_vid, second_row = rows[1]
    print("初始选中:", home._selected)

    # 找到第二行里显示版本号的那个 Label —— 也就是以前点不中的地方
    target = None
    for lbl in labels(second_row):
        try:
            if lbl.cget("text") == second_vid:
                target = lbl
                break
        except tk.TclError:
            continue
    if target is None:
        print("没找到版本名 Label")
        app.destroy()
        return 2

    target.event_generate("<Button-1>", x=5, y=5)
    app.update()
    app.update_idletasks()

    print("点完选中:", home._selected)
    ok = home._selected == second_vid
    print("行底色 disabled/enabled:", "OK" if ok else "FAIL")
    print("选中态:", {k: r._selected for k, r in home._rows.items()})
    app.destroy()
    return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
