"""继续挖「切主题后设置页卡死」：这次看几何和可交互性。

上一版探针只扫了两层子控件，没找到 FlatButton；这次递归全树，并且重点看
1. 设置页子树里每个关键控件的几何（是不是塌成 0）；
2. ScrollFrame 的 inner 宽度有没有同步（不同步 = 内容被裁掉/看不见）；
3. 真实点击设置页按钮是否触发；
4. 主题按钮的选中态是否跟着换。
"""
from __future__ import annotations

import sys
import time
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FAIL: list[str] = []


def check(cond, msg):
    if not cond:
        FAIL.append(msg)
    print(("  ok   " if cond else "  FAIL ") + msg)


def settle(app, sec=1.0):
    end = time.time() + sec
    while time.time() < end:
        app.update()
        time.sleep(0.02)


def walk(w, depth=0, limit=6):
    if depth > limit:
        return
    try:
        kids = w.winfo_children()
    except tk.TclError:
        return
    for k in kids:
        yield k, depth
        yield from walk(k, depth + 1, limit)


def find(w, cls_name, limit=8):
    out = []
    for child, _d in walk(w, limit=limit):
        if child.__class__.__name__ == cls_name:
            out.append(child)
    return out


def click(app, widget):
    settle(app, 0.1)
    try:
        x, y = widget.winfo_width() // 2, widget.winfo_height() // 2
        widget.event_generate("<Button-1>", x=x, y=y)
        widget.event_generate("<ButtonRelease-1>", x=x, y=y)
    except tk.TclError as exc:
        print("  event_generate 失败:", exc)
        return False
    settle(app, 0.3)
    return True


def report(app, tag):
    ps = app._pages["settings"]
    print(f"\n--- {tag}")
    print(f"  settings 页 宽高: {ps.winfo_width()}x{ps.winfo_height()} "
          f"mapped={ps.winfo_ismapped()}")
    # root / head / scroll / box
    kids = ps.winfo_children()
    print(f"  直接子控件 {len(kids)} 个: "
          f"{[(k.__class__.__name__, k.winfo_width(), k.winfo_height()) for k in kids]}")
    sfs = find(ps, "ScrollFrame")
    for sf in sfs:
        inner = sf.inner
        cv = sf._canvas
        print(f"  ScrollFrame: canvas {cv.winfo_width()}x{cv.winfo_height()}, "
              f"inner {inner.winfo_width()}x{inner.winfo_height()}, "
              f"item width={cv.itemcget(sf._win, 'width')!r}, "
              f"scrollregion={cv.cget('scrollregion')!r}")
        check(inner.winfo_width() > 100,
              f"{tag}: 设置页内容区宽度正常（{inner.winfo_width()}）")
        check(abs(inner.winfo_width() - cv.winfo_width()) <= 40,
              f"{tag}: 内容区宽度与画布同步（inner={inner.winfo_width()} canvas={cv.winfo_width()}）")
    # 主题按钮选中态
    btns = getattr(ps, "_theme_btns", {})
    print(f"  主题按钮 {len(btns)} 个，选中提示: "
          f"{[(k, getattr(b, 'kind', '?')) for k, b in btns.items()]}")
    # 找到「保存设置」
    all_btn = find(ps, "FlatButton")
    print(f"  FlatButton 共 {len(all_btn)} 个，宽度样本: "
          f"{[b.winfo_width() for b in all_btn[:6]]}")
    check(len(all_btn) > 5, f"{tag}: 设置页按钮都在（{len(all_btn)} 个）")
    return ps, all_btn


def main() -> int:
    from mclite.ui.app import App

    app = App()
    app.create_pages()
    app.show_page("settings")
    settle(app, 1.5)
    report(app, "切主题前")

    for name in ("dark", "pcl"):
        ps = app._pages["settings"]
        print(f"\n=== 切主题 {name}")
        ps._set_theme(name)
        settle(app, 2.0)
        ps, btns = report(app, f"切到 {name} 后")

        # 点「保存设置」（head 里第一个 FlatButton，文字是「保存设置」）
        target = None
        for b in btns:
            if getattr(b, "_text", "").strip() == "保存设置" or "保存" in str(getattr(b, "_text", "")):
                target = b
                break
        if target is None:
            target = btns[0] if btns else None
        hit = {"n": 0}
        if target is not None:
            orig = ps.save_all
            ps.save_all = lambda: hit.__setitem__("n", hit["n"] + 1)
            click(app, target)
            ps.save_all = orig
        check(hit["n"] == 1, f"切到 {name} 后点击设置页按钮能触发（hits={hit['n']}）")

        # 主题按钮选中态是否只剩一个 accent_soft
        selects = [k for k, b in getattr(ps, "_theme_btns", {}).items()
                   if getattr(b, "kind", "") == "accent_soft"]
        print(f"  选中态按钮: {selects}")
        check(selects == [name] or (len(selects) == 1),
              f"切到 {name} 后选中态唯一（{selects}）")

    app.destroy()
    print()
    print(f"FAIL {len(FAIL)} 项")
    for f in FAIL:
        print("  - " + f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
