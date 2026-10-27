"""dump 某页某列的子树高度，看哪块把纵向空间吃掉了。

用法：python tools/probe_vheight.py [page] [w] [h] [column]
column: page | body | right
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
    print(f"=== {page} page={p.winfo_width()}x{p.winfo_height()}")
    targets = [p] + [getattr(p, n, None) for n in ("_tab_launch", "_body", "_left", "_right")]
    for t in targets:
        if t is None:
            continue
        try:
            print(f"  {str(t)[-30:]:30s} req={t.winfo_reqheight():4d} got={t.winfo_height():4d}")
            for c in t.winfo_children():
                print(f"    {c.winfo_class():10s} req={c.winfo_reqheight():4d} "
                      f"got={c.winfo_height():4d} {str(c)[-20:]}")
        except Exception:
            pass
    a.destroy()


if __name__ == "__main__":
    main()
