"""量页面纵向溢出：哪个控件的下边界超出了页面高度。

用法：python tools/probe_vclip.py [page] [w] [h]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    from mclite.ui import app as A

    page = sys.argv[1] if len(sys.argv) > 1 else "home"
    gw = int(sys.argv[2]) if len(sys.argv) > 2 else 882
    gh = int(sys.argv[3]) if len(sys.argv) > 3 else 560
    a = A.App()
    a.update()
    a.create_pages()
    a.show_page(page)
    a.geometry(f"{gw}x{gh}")
    end = time.time() + 2.0
    while time.time() < end:
        a.update()
        time.sleep(0.02)
    p = a._pages[page]
    pw, ph = p.winfo_width(), p.winfo_height()
    print(f"=== {page} {gw}x{gh} page={pw}x{ph}")
    over = []
    stack = [p]
    while stack:
        node = stack.pop()
        try:
            kids = node.winfo_children()
        except Exception:
            continue
        stack.extend(kids)
        try:
            if not node.winfo_ismapped():
                continue
            y = node.winfo_rooty() - p.winfo_rooty()
            h = node.winfo_height()
            x = node.winfo_rootx() - p.winfo_rootx()
            w = node.winfo_width()
        except Exception:
            continue
        if y + h > ph + 1 or x + w > pw + 1:
            label = ""
            try:
                if node.winfo_class() in ("Label", "Canvas"):
                    label = str(node.cget("text") or "")[:20]
            except Exception:
                pass
            over.append((y + h - ph, x + w - pw, node.winfo_class(), label, str(node)[-40:]))
    over.sort(reverse=True)
    for oy, ox, cls, label, path in over[:15]:
        print(f"  bottom+{oy:4d} right+{ox:4d} {cls:10s} {label!r} {path}")
    print(f"  共 {len(over)} 个越界")
    a.destroy()


if __name__ == "__main__":
    main()
