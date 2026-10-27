"""dump 某页右栏子树 reqwidth，找出谁把宽度顶住了。

用法：python tools/probe_right_tree.py [home|install] [min_req]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    from mclite.ui import app as A

    page = sys.argv[1] if len(sys.argv) > 1 else "home"
    floor = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    a = A.App()
    a.update()
    a.create_pages()
    a.show_page(page)
    end = time.time() + 1.8
    while time.time() < end:
        a.update()
        time.sleep(0.02)
    p = a._pages[page]
    right = getattr(p, "_right", None)
    print(f"=== {page} page={p.winfo_width()} right req={right.winfo_reqwidth()}")
    stack = [(right, 0)]
    while stack:
        node, d = stack.pop()
        try:
            req = node.winfo_reqwidth()
            got = node.winfo_width()
            cls = node.winfo_class()
        except Exception:
            continue
        if req >= floor:
            label = ""
            try:
                if cls in ("Label", "Canvas"):
                    label = str(node.cget("text") or "")[:24]
            except Exception:
                pass
            print(f"{'  ' * d}req={req:4d} got={got:4d} {cls:10s} {label!r} {str(node)[-46:]}")
        try:
            for c in node.winfo_children():
                stack.append((c, d + 1))
        except Exception:
            pass
    a.destroy()


if __name__ == "__main__":
    main()
