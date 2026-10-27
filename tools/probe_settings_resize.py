"""看设置页 on_resize 是否被调用、怎么改 wraplength。

用法：python tools/probe_settings_resize.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mclite.ui import app as A


def pump(a, sec=1.6):
    end = time.time() + sec
    while time.time() < end:
        try:
            a.update()
        except Exception:
            return
        time.sleep(0.02)


def main() -> None:
    a = A.App()
    a.update()
    a.create_pages()
    a.show_page("settings")
    a.geometry("882x560")
    pump(a, 1.8)

    p = a._pages["settings"]
    print("has on_resize:", hasattr(p, "on_resize"))
    print("calling on_resize(651) manually")
    p.on_resize(651)
    pump(a, 1.0)

    def walk(w, depth=0):
        for c in w.winfo_children():
            try:
                if c.winfo_class() == "Label":
                    txt = str(c.cget("text") or "")[:26].replace("\n", "\\n")
                    if txt:
                        print(f"  {'  ' * depth}got={c.winfo_width():4d} req={c.winfo_reqwidth():4d} "
                              f"wrap={c.cget('wraplength')} {txt!r}")
            except Exception:
                pass
            walk(c, depth + 1)

    walk(p)
    a.destroy()


if __name__ == "__main__":
    main()
