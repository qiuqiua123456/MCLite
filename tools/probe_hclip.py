"""列出各页面在窄窗口下横向越界（被窗口右边缘裁掉）的控件。

用于「窗口往小调整时按键要完整显示」这条需求的定位与验收。

用法：
    python tools/probe_hclip.py [宽x高 ...]

默认测 1160x724 / 1000x640 / 900x580 / 882x560 四档。
"""

from __future__ import annotations

import subprocess
import sys
import time

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from mclite.ui import app as A


def walk(w, out, depth=0):
    try:
        kids = w.winfo_children()
    except Exception:
        return
    for c in kids:
        out.append((c, depth))
        walk(c, out, depth + 1)


def pump(a, sec=0.8):
    end = time.time() + sec
    while time.time() < end:
        try:
            a.update()
        except Exception:
            return
        time.sleep(0.02)


SIZES = [(1160, 724), (1000, 640), (900, 580), (882, 560)]


def one(page: str, gw: int, gh: int) -> None:
    """在独立进程里测一个 (页面, 尺寸) 组合。

    不能在同一进程里连着建 App()：`mclite/ui/images.py` 的 `_CACHE` 会把
    属于上一个 root 的 PhotoImage 留着，第二次 build 时
    `hero.width()` 抛 `application has been destroyed`。
    """
    a = A.App()
    a.update()
    a.create_pages()
    a.show_page(page)
    a.geometry(f"{gw}x{gh}")
    pump(a, 1.2)
    p = a._pages[page]
    px = p.winfo_rootx()
    py = p.winfo_rooty()
    pw = p.winfo_width()
    ph = p.winfo_height()
    real = f"{a.winfo_width()}x{a.winfo_height()}"
    items = []
    walk(p, items)
    bad = []
    for c, d in items:
        try:
            if not c.winfo_ismapped():
                continue
            w = c.winfo_width()
            req = c.winfo_reqwidth()
        except Exception:
            continue
        # 真正的「被切掉」信号是「实际宽度小于它要求的宽度」：pack/grid 在空间
        # 不够时会把控件压窄，按钮文字、标签就露不全了。用 req 而不是「超出父控件
        # 右边缘」判断，是因为 Canvas 里的长列表天生就超出可见区（那是滚动内容）。
        if req > 10 and w + 2 < req:
            bad.append((req - w, c.winfo_class(), str(c), c.winfo_x(), c.winfo_y(), w, c.winfo_height(), req))
    bad.sort(reverse=True)
    print(f"=== {page:8s} 请求 {gw}x{gh} 实际 {real} page={pw}x{ph} 横向越界 {len(bad)} 个")
    for b in bad[:8]:
        print(
            f"    +{b[0]:4d}px {b[1]:10s} {b[2][-26:]:26s} x={b[3]:4d} y={b[4]:4d} "
            f"w={b[5]:4d} h={b[6]:3d} d={b[7]}"
        )
    a.destroy()


def main():
    if len(sys.argv) == 4 and sys.argv[1] in ("home", "install", "settings"):
        one(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
        return

    sizes = []
    for spec in sys.argv[1:]:
        w, h = spec.lower().split("x")
        sizes.append((int(w), int(h)))
    if not sizes:
        sizes = SIZES

    for gw, gh in sizes:
        for page in ("home", "install", "settings"):
            subprocess.run(
                [sys.executable, "-u", __file__, page, str(gw), str(gh)],
                check=False,
            )
        print()


if __name__ == "__main__":
    main()
