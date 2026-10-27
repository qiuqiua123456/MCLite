"""量 home 右栏滚动区的内外高度，确认大窗口下不该出现滚动条。

用法：python tools/probe_right_scroll.py [w] [h]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    from mclite.ui import app as A

    gw = int(sys.argv[1]) if len(sys.argv) > 1 else 1162
    gh = int(sys.argv[2]) if len(sys.argv) > 2 else 724
    a = A.App()
    a.update()
    a.create_pages()
    a.show_page("home")
    a.geometry(f"{gw}x{gh}")
    end = time.time() + 1.8
    while time.time() < end:
        a.update()
        time.sleep(0.02)
    p = a._pages["home"]
    sc = p._right_scroll
    print(f"window {a.winfo_width()}x{a.winfo_height()} page {p.winfo_width()}x{p.winfo_height()}")
    print(f"  scrollframe  {sc.winfo_width()}x{sc.winfo_height()}")
    print(f"  canvas       {sc._canvas.winfo_width()}x{sc._canvas.winfo_height()}")
    print(f"  inner        {sc.inner.winfo_width()}x{sc.inner.winfo_height()} "
          f"req={sc.inner.winfo_reqwidth()}x{sc.inner.winfo_reqheight()}")
    print(f"  scrollregion {sc._canvas.cget('scrollregion')!r}")
    for c in sc.inner.winfo_children():
        print(f"    child {c.winfo_class():10s} req_h={c.winfo_reqheight():4d} "
              f"got_h={c.winfo_height():4d} bg={c.cget('bg')}")
    print(f"  actions_slot {p._actions_slot.winfo_height()}  "
          f"actions {p._actions.winfo_height()}")
    a.destroy()


if __name__ == "__main__":
    main()
