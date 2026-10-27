"""量出各页面「右侧面板」各行真正需要多宽，用来决定左栏能让出多少。

在 1160x724 下 dump 每个 row/section 的 reqwidth 与实际宽度，
req 明显大于实际的就是在窄窗口下会被压扁的那一行。
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mclite.ui import app as A


def pump(a, sec=0.8):
    end = time.time() + sec
    while time.time() < end:
        try:
            a.update()
        except Exception:
            return
        time.sleep(0.02)


def dump(w, label, depth=0):
    try:
        kids = w.winfo_children()
    except Exception:
        return
    for c in kids:
        try:
            m = c.winfo_manager()
            cls = c.winfo_class()
            rw, rh = c.winfo_reqwidth(), c.winfo_reqheight()
            ww, wh = c.winfo_width(), c.winfo_height()
            txt = ""
            try:
                txt = str(c.cget("text"))[:24]
            except Exception:
                pass
        except Exception:
            continue
        print(
            f"  {'  ' * depth}{label}/{str(c).split('.')[-1]:<12} {cls:<9} "
            f"req={rw:4d}x{rh:<4d} got={ww:4d}x{wh:<4d} mgr={m or '-':<6} {txt}",
            flush=True,
        )
        if depth < 2 and rw > 40:
            dump(c, label, depth + 1)


def one(page: str) -> None:
    a = A.App()
    a.update()
    a.create_pages()
    a.show_page(page)
    a.geometry("1160x724")
    pump(a, 1.4)
    p = a._pages[page]
    print(f"=== {page} page={p.winfo_width()}x{p.winfo_height()}", flush=True)
    dump(p, page)
    a.destroy()


def main():
    if len(sys.argv) > 1:
        one(sys.argv[1])
        return
    for page in ("home", "install", "settings"):
        subprocess.run([sys.executable, "-u", __file__, page], check=False)


if __name__ == "__main__":
    main()
