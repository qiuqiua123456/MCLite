"""走真实 app 路径（改窗口大小）看 on_resize 有没有生效。

用法：python tools/probe_app_resize.py [page]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mclite.ui import app as A
from mclite.ui import responsive

CALLS = []
_orig_wrap = responsive.wrap_labels
_orig_fix = responsive.fix_clipped


def wrap_spy(root, width, min_width=60):
    n = _orig_wrap(root, width, min_width)
    CALLS.append(("wrap", int(width), n))
    return n


def fix_spy(root, min_width=56):
    n = _orig_fix(root, min_width)
    CALLS.append(("fix", 0, n))
    return n


responsive.wrap_labels = wrap_spy
responsive.fix_clipped = fix_spy


def pump(a, sec):
    end = time.time() + sec
    while time.time() < end:
        try:
            a.update()
        except Exception:
            return
        time.sleep(0.02)


def main() -> None:
    page = sys.argv[1] if len(sys.argv) > 1 else "settings"
    a = A.App()
    a.update()
    a.create_pages()
    a.show_page(page)
    pump(a, 1.2)
    CALLS.clear()
    print("--- resize to 882x560")
    a.geometry("882x560")
    pump(a, 1.6)
    print("calls:", CALLS)
    p = a._pages[page]
    print("page:", p.winfo_width(), "x", p.winfo_height())
    for c in ("_java_list", "_jdk_hint", "_login_row"):
        w = getattr(p, c, None)
        if w is not None:
            print(f"  {c}: wrap={w.cget('wraplength') if hasattr(w, 'cget') else '-'} "
                  f"req={w.winfo_reqwidth()} got={w.winfo_width()}")
    a.destroy()


if __name__ == "__main__":
    main()
