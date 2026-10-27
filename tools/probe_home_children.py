"""home 页面逐个子控件剥离：找出拖动卡顿到底出在哪一块。

修正后的测量结论（每档独立进程、只测一轮）：
```
baseline（现状）                37.8–38.2 ms
shell_only（所有页面 hide）      15.1 ms
page_blank（home 子控件全 hide） 14.7 ms   ← 成本全在 home 页面的子控件里
no_topbar                       80.5 ms   ← 去掉顶栏更慢，说明顶栏不是主因
no_side                         39.3 ms
```

`page_blank` 已经证明成本在 home 页面的子控件里，这个脚本逐个 hide 它们，看哪
一块是主要贡献。用法：`python tools/probe_home_children.py <list|hide:N>`
"""
from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

WIDTH_START = 1120
WIDTH_END = 1300
STEP = 4
FRAME_MS = 16


def measure(app) -> tuple[float, float]:
    delays: list[float] = []
    widths = list(range(WIDTH_START, WIDTH_END, STEP))
    it = {"i": 0, "last": time.perf_counter()}

    def beat() -> None:
        now = time.perf_counter()
        delays.append(max(0.0, (now - it["last"]) * 1000.0 - FRAME_MS))
        it["last"] = now
        i = it["i"]
        if i < len(widths):
            it["i"] = i + 1
            app.geometry(f"{widths[i]}x724")
            app.after(FRAME_MS, beat)

    app.after(FRAME_MS, beat)
    deadline = time.perf_counter() + 30
    while it["i"] < len(widths) and time.perf_counter() < deadline:
        app.update()
        time.sleep(0.002)
    end = time.perf_counter() + 0.4
    while time.perf_counter() < end:
        app.update()
        time.sleep(0.005)
    over = delays[3:]
    return (statistics.median(over) if over else 0.0, max(over) if over else 0.0)


def describe(w) -> str:
    """给控件一个可读的名字：class + 尺寸 + 前几个子控件。"""
    try:
        kids = w.winfo_children()
    except Exception:                          # noqa: BLE001
        kids = []
    text = ""
    try:
        text = w.cget("text")
    except Exception:                          # noqa: BLE001
        pass
    tag = f"{w.winfo_class():8s} {w.winfo_width():4d}x{w.winfo_height():<4d}"
    if text:
        tag += f" 「{str(text)[:14]}」"
    tag += f" kids={len(kids)}"
    return tag


def walk(w, path="0", depth=0, out=None):
    """递归列出子树，path 形如 '0.0.1'（不含 page 根）。"""
    if out is None:
        out = []
    for i, c in enumerate(w.winfo_children()):
        p = f"{path}.{i}" if path else str(i)
        out.append((p, depth, c))
        walk(c, p, depth + 1, out)
    return out


def main() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else "list"
    max_depth = int(sys.argv[2]) if len(sys.argv) > 2 else 99

    from mclite.ui import app as app_mod

    app = app_mod.App()
    app.create_pages()
    app.update()
    app.show_page("home")
    for _ in range(60):
        app.update()
        time.sleep(0.01)

    page = app._pages["home"]
    nodes = walk(page, path="")
    index = {p: w for p, _d, w in nodes}

    if arg == "list":
        for p, d, w in nodes:
            if d < max_depth:
                print(f"  {p:14s} {'  ' * d}{describe(w)}")
        print(f"  合计 {len(nodes)} 个控件")
        app.destroy()
        return 0

    if arg.startswith("hide:"):
        spec = arg.split(":", 1)[1]
        if spec == "root":
            targets = [page]
        elif spec == "all":
            targets = [w for _p, _d, w in nodes]
        else:
            targets = [index[p] for p in spec.split(",") if p in index]

        for w in targets:
            mgr = w.winfo_manager()
            try:
                if mgr == "pack":
                    w.pack_forget()
                elif mgr == "place":
                    w.place_forget()
                elif mgr == "grid":
                    w.grid_forget()
            except Exception:                  # noqa: BLE001
                pass
        for _ in range(40):
            app.update()
            time.sleep(0.01)

    mid, worst = measure(app)
    app.destroy()
    print(f'hide={arg}  mid={mid:.1f}  worst={worst:.1f}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
