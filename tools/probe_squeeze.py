"""列出窄窗口下被压窄（req > got+2）的控件，带类名与文字。

用法：
    python tools/probe_squeeze.py home 882 560
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mclite.ui import app as A


def walk(w, depth=0, out=None):
    if out is None:
        out = []
    for c in w.winfo_children():
        try:
            if c.winfo_ismapped():
                out.append((c, depth))
        except Exception:
            pass
        walk(c, depth + 1, out)
    return out


def one(page: str, gw: int, gh: int) -> None:
    a = A.App()
    a.update()
    a.create_pages()
    a.show_page(page)
    a.geometry(f"{gw}x{gh}")
    end = time.time() + 1.4
    while time.time() < end:
        try:
            a.update()
        except Exception:
            break
        time.sleep(0.02)
    p = a._pages[page]
    rows = []
    for c, d in walk(p):
        try:
            req = c.winfo_reqwidth()
            got = c.winfo_width()
            if req > 10 and got + 2 < req:
                txt = ""
                try:
                    txt = str(c.cget("text"))[:24]
                except Exception:
                    txt = ""
                rows.append((req - got, d, c.winfo_class(), txt, got, req, c.winfo_x(), c.winfo_y(),
                             str(c)[-46:]))
        except Exception:
            continue
    rows.sort(reverse=True)
    print(f"=== {page} {gw}x{gh} page={p.winfo_width()}x{p.winfo_height()} 被压 {len(rows)} 个")
    for over, d, cls, txt, got, req, x, y, path in rows[:18]:
        print(f"  +{over:4d}px {'  ' * d}{cls:10s} got={got:4d} req={req:4d} "
              f"x={x:4d} y={y:3d} {txt!r} {path}")
    a.destroy()


def main() -> None:
    if len(sys.argv) == 4:
        one(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
        return
    for page in ("home", "install", "settings"):
        subprocess.run([sys.executable, "-u", __file__, page, "882", "560"], check=False)
        print()


if __name__ == "__main__":
    main()
