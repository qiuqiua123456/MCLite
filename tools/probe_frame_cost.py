"""每帧成本：46 次「改宽度 → 强制布局 → 强制重绘」的总耗时 / 帧数。

心跳延迟法受机器噪声影响太大（同档中位在 15–150 ms 之间跳），没法做 A/B。
这里改用**确定性**的指标：固定改 46 次宽度，每次都 `update_idletasks() +
update()` 把布局和重绘都逼完，量总耗时 / 46。同一个进程里每帧都做完，不存在
「上一次的活儿漏到下一次」的问题。

用法：python tools/probe_frame_cost.py <mode>
mode: baseline | no_page | no_page_children | no_list | no_hero | no_topbar
      | no_side | no_scroll_width | topbar_nodraw
"""
from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

WIDTHS = list(range(1120, 1300, 4))          # 46 帧


def hide(w) -> bool:
    try:
        mgr = w.winfo_manager()
        if mgr == "pack":
            w.pack_forget()
        elif mgr == "place":
            w.place_forget()
        elif mgr == "grid":
            w.grid_forget()
        else:
            return False
        return True
    except Exception:                          # noqa: BLE001
        return False


def walk(w, out=None):
    if out is None:
        out = []
    for c in w.winfo_children():
        out.append(c)
        walk(c, out)
    return out


def frame_cost(app) -> tuple[float, float, float]:
    """返回 (总耗时/46, 其中布局/46, 其中重绘/46) ms。"""
    total = idle = draw = 0.0
    for w in WIDTHS:
        t0 = time.perf_counter()
        app.geometry(f"{w}x724")
        t1 = time.perf_counter()
        app.update_idletasks()
        t2 = time.perf_counter()
        app.update()
        t3 = time.perf_counter()
        total += (t3 - t0) * 1000.0
        idle += (t2 - t1) * 1000.0
        draw += (t3 - t2) * 1000.0
    n = len(WIDTHS)
    return total / n, idle / n, draw / n


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "baseline"

    from mclite.ui import app as app_mod

    app = app_mod.App()
    app.create_pages()
    app.update()
    app.show_page("home")
    for _ in range(60):
        app.update()
        time.sleep(0.01)

    page = app._pages["home"]
    note = mode
    nodes = walk(page)

    if mode == "no_page":
        page.place_forget()
        note = "页面 place_forget"
    elif mode == "no_page_children":
        for w in page.winfo_children():
            hide(w)
        note = "页面子控件全 hide"
    elif mode == "no_list":
        # 版本列表的 ScrollFrame 是 0.1.0.0.1.0.2
        target = None
        for w in nodes:
            if w.winfo_class() == "Canvas" and w.winfo_height() > 300 and w.winfo_width() > 300:
                target = w.master
        if target is not None:
            hide(target)
            note = f"隐藏版本列表 {target.winfo_width()}x{target.winfo_height()}"
        else:
            note = "no_list 未找到目标"
    elif mode == "no_hero":
        n = 0
        for w in nodes:
            if w.winfo_class() == "Canvas" and w.winfo_height() > 80 and not w.winfo_children():
                if hide(w):
                    n += 1
        note = f"隐藏 {n} 个 Canvas（hero + 按钮）"
    elif mode == "no_topbar":
        hide(app._topbar)
        note = "顶栏 hide"
    elif mode == "no_side":
        hide(app._side)
        note = "左侧栏 hide"
    elif mode == "no_scroll_width":
        from mclite.ui import theme as _t
        _t.ScrollFrame._flush_width = lambda self: None
        _t.ScrollFrame._on_canvas_configure = lambda self, e: None
        note = "禁用 ScrollFrame 宽度同步"
    elif mode == "topbar_nodraw":
        app._topbar._draw = lambda *a, **k: None
        note = "顶栏不重画"
    elif mode.startswith("grad"):
        # grad24 / grad32 / grad48 / grad80：渐变段数
        steps = int(mode[4:])
        import mclite.ui.app as _app

        def fewer(canvas, w, h, c1, c2, steps=110, tag="grad"):
            return _orig_grad(canvas, w, h, c1, c2, steps=steps, tag=tag)

        _orig_grad = _app.gradient
        _app.gradient = fewer
        bar = app._topbar
        bar._bg_w = -1
        bar._draw()
        note = f"渐变 {steps} 段"
    elif mode == "topbar_solid":
        # 只画一条纯色矩形，不画任何前景
        bar = app._topbar

        def solid(*_a, **_k):
            bar.delete("all")
            bar.create_rectangle(0, 0, bar.winfo_width(), bar.winfo_height(),
                                 fill="#0E5FB8", outline="")

        bar._draw = solid
        note = "顶栏只画一条纯色"
    elif mode == "topbar_image":
        # 渐变换成 1 张 PhotoImage，前景照画
        import tkinter as tk
        from mclite.ui import theme as _t
        import mclite.ui.app as _app

        bar = app._topbar
        cache = {"w": -1, "img": None}

        def make(w):
            steps = max(2, min(w, 256))
            row = "{" + " ".join(_t.mix(_t.ACCENT_DARK, _t.ACCENT_HOVER, i / (steps - 1))
                                 for i in range(steps)) + "}"
            img = tk.PhotoImage(master=bar, width=steps, height=1)
            img.put(row)
            return img.zoom(max(1, round(w / steps)), bar.winfo_height() or 48)

        def bg_image(canvas, w, h, c1, c2, steps=110, tag="grad"):
            if cache["w"] != w or cache["img"] is None:
                cache["img"] = make(w)
                cache["w"] = w
            canvas.create_image(0, 0, anchor="nw", image=cache["img"], tags=tag)
            bar._bgimg = cache["img"]          # 防 GC

        _app.gradient = bg_image
        bar._bg_w = -1
        bar._draw()
        note = "顶栏渐变改 PhotoImage"
    elif mode == "topbar_no_text":
        bar = app._topbar
        bar.create_text = lambda *a, **k: 0
        bar._draw()
        note = "顶栏不写字"
    elif mode == "topbar_no_avatar":
        bar = app._topbar
        bar.create_window = lambda *a, **k: 0
        bar._draw()
        note = "顶栏不嵌 Avatar"
    elif mode == "topbar_no_round":
        import mclite.ui.app as _app
        import mclite.ui.theme as _t

        def flat(canvas, x0, y0, x1, y1, r, **kw):
            canvas.create_rectangle(x0, y0, x1, y1, **kw)

        _t.round_rect = flat
        _app.round_rect = flat
        bar = app._topbar
        bar._draw()
        note = "顶栏圆角改直角"

    for _ in range(40):
        app.update()
        time.sleep(0.01)

    rounds = []
    for _ in range(3):
        rounds.append(frame_cost(app)[0])
    # 拆一次给参考
    t, i, d = frame_cost(app)

    app.destroy()
    med = statistics.median(rounds)
    print(f"{mode:18s} 帧成本 中位 {med:6.2f} | 拆: 布局 {i:5.2f} 重绘 {d:5.2f} | {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
