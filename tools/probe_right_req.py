"""看 home/install 右栏 reqwidth，用来决定左栏最少能留多宽。

用法：python tools/probe_right_req.py [home|install]
（每次只测一页：同进程建第二个 App 会崩，所以两页要分两次跑。）
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    from mclite.ui import app as A

    page = sys.argv[1] if len(sys.argv) > 1 else "home"
    a = A.App()
    a.update()
    a.create_pages()
    a.show_page(page)
    end = time.time() + 1.8
    while time.time() < end:
        a.update()
        time.sleep(0.02)
    p = a._pages[page]
    print(f"=== {page} page={p.winfo_width()}x{p.winfo_height()}")
    for name in ("_body", "_left", "_right", "_tools", "_manage", "_act",
                 "_hero_canvas", "_scroll", "_big_name"):
        w = getattr(p, name, None)
        if w is None:
            print(f"  {name:12s} (无)")
            continue
        try:
            print(f"  {name:12s} req={w.winfo_reqwidth():4d} got={w.winfo_width():4d}")
        except Exception as e:                        # noqa: BLE001
            print(f"  {name:12s} err {e}")
    right = getattr(p, "_right", None)
    if right is not None:
        kids = []
        for c in right.winfo_children():
            try:
                kids.append((c.winfo_reqwidth(), c.winfo_class(), str(c)))
            except Exception:
                pass
        kids.sort(reverse=True)
        for req, cls, path in kids[:6]:
            print(f"   right child req={req:4d} {cls:8s} {path}")
    a.destroy()


if __name__ == "__main__":
    main()
