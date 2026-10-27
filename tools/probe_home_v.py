"""量 home 右栏每一块的纵向需求，看小窗口下超出多少。

用法：python tools/probe_home_v.py [w] [h]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    from mclite.ui import app as A

    gw = int(sys.argv[1]) if len(sys.argv) > 1 else 882
    gh = int(sys.argv[2]) if len(sys.argv) > 2 else 560
    a = A.App()
    a.update()
    a.create_pages()
    a.show_page("home")
    a.geometry(f"{gw}x{gh}")
    end = time.time() + 2.0
    while time.time() < end:
        a.update()
        time.sleep(0.02)
    p = a._pages["home"]
    body = p._body
    right = p._right
    print(f"page={p.winfo_width()}x{p.winfo_height()} body={body.winfo_width()}x{body.winfo_height()}")
    print(f"body req height = {body.winfo_reqheight()}")
    print(f"right req = {right.winfo_reqwidth()}x{right.winfo_reqheight()} "
          f"got={right.winfo_width()}x{right.winfo_height()}")
    for c in right.winfo_children():
        extra = ""
        try:
            kids = c.winfo_children()
            extra = " | ".join(f"{k.winfo_class()}:{k.winfo_reqheight()}" for k in kids)
        except Exception:
            pass
        print(f"  {c.winfo_class():10s} req_h={c.winfo_reqheight():4d} "
              f"got_h={c.winfo_height():4d}  {extra}")
    a.destroy()


if __name__ == "__main__":
    main()
