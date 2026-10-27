"""放松 minsize，看更小的尺寸下还有多少控件被压。

用法：python tools/probe_min_size.py home 760 470
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def one(page: str, gw: int, gh: int) -> None:
    from mclite.ui import app as A

    a = A.App()
    a.update()
    a.minsize(560, 420)          # 放开限制，测真实布局能力
    a.create_pages()
    a.show_page(page)
    a.geometry(f"{gw}x{gh}")
    end = time.time() + 1.6
    while time.time() < end:
        try:
            a.update()
        except Exception:
            break
        time.sleep(0.02)
    p = a._pages[page]
    rows = []
    stack = [p]
    while stack:
        c = stack.pop()
        try:
            stack.extend(c.winfo_children())
            if not c.winfo_ismapped():
                continue
            req, got = c.winfo_reqwidth(), c.winfo_width()
        except Exception:
            continue
        if req > 10 and got + 2 < req:
            txt = ""
            try:
                txt = str(c.cget("text"))[:22]
            except Exception:
                pass
            rows.append((req - got, c.winfo_class(), txt, got, req, str(c)[-38:]))
    rows.sort(reverse=True)
    print(f"=== {page} 请求 {gw}x{gh} 实际 {a.winfo_width()}x{a.winfo_height()} "
          f"page={p.winfo_width()}x{p.winfo_height()} 被压 {len(rows)} 个")
    for over, cls, txt, got, req, path in rows[:10]:
        print(f"  +{over:4d}px {cls:10s} got={got:4d} req={req:4d} {txt!r} {path}")
    a.destroy()


if __name__ == "__main__":
    one(sys.argv[1] if len(sys.argv) > 1 else "home",
        int(sys.argv[2]) if len(sys.argv) > 2 else 760,
        int(sys.argv[3]) if len(sys.argv) > 3 else 470)
