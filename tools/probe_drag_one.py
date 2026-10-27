"""单档测量器：一次进程只测一种状态，输出一行 JSON。

两个关键设计（都是踩过坑才定下来的）：

1. **每档独立进程**。同一进程里连续测同一状态会漂移（app 上 76 → 115 → 146 ms），
   而空窗口五轮稳定 15.0 ms。所以 `probe_drag_ab.py` 用子进程逐个调用本脚本。
2. **`geometry()` 必须放在心跳回调里面、`after` 重新计时放在它之后**。这样下一
   次心跳的间隔天然包含「改宽度 → 系统重排重绘」的成本；如果改成外部 driver
   循环按 16ms 节奏改宽度，driver 自己的 sleep 会把抖动吸收掉，测出来永远是
   16ms，完全是假数字。
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

STEP_MS = 16
ROUNDS = int(__import__("os").environ.get("PROBE_ROUNDS", "1"))


def drain(app, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.update()
        time.sleep(0.005)


def drag(app, start=1120, end=1300, step=4) -> dict:
    app.geometry(f"{start}x724")
    drain(app, 0.4)
    widths = list(range(start, end + 1, step))
    lateness, it = [], {"i": 0, "last": time.perf_counter()}

    def beat():
        now = time.perf_counter()
        lateness.append(max(0.0, (now - it["last"]) * 1000.0 - STEP_MS))
        it["last"] = now
        i = it["i"]
        if i < len(widths):
            it["i"] = i + 1
            app.geometry(f"{widths[i]}x724")
            app.after(STEP_MS, beat)

    app.after(STEP_MS, beat)
    deadline = time.perf_counter() + 40
    while it["i"] < len(widths) and time.perf_counter() < deadline:
        app.update()
        time.sleep(0.002)
    drain(app, 0.8)
    n = len(lateness)
    return {"mid": statistics.median(lateness), "p90": sorted(lateness)[int(n * 0.9)],
            "worst": max(lateness), "over": sum(1 for v in lateness if v > 16.6), "n": n}


def apply_mode(app, page, mode: str) -> None:
    import tkinter as tk

    if mode == "baseline":
        return
    if mode == "no_page":
        page.place_forget()
    elif mode == "no_page_content":
        for w in list(page.winfo_children()):
            try:
                if w.winfo_manager() == "pack":
                    w.pack_forget()
                elif w.winfo_manager() == "place":
                    w.place_forget()
            except Exception:                  # noqa: BLE001
                pass
    elif mode == "no_hero":
        stack = [page]
        while stack:
            w = stack.pop()
            if isinstance(w, tk.Canvas):
                try:
                    if any(w.type(i) == "image" for i in w.find_all()):
                        w.pack_forget()
                        continue
                except Exception:              # noqa: BLE001
                    pass
            try:
                stack.extend(w.winfo_children())
            except Exception:                  # noqa: BLE001
                pass
    elif mode == "no_side":
        app._side.pack_forget()
    elif mode == "no_topbar":
        app._topbar.pack_forget()
    elif mode == "no_toast_side":
        app._side.pack_forget()
        app._topbar.pack_forget()
    elif mode == "plain_topbar":
        # 同样高度、同样是 Frame，但不画渐变、不画文字
        h = app._topbar.winfo_height()
        app._topbar.pack_forget()
        alt = tk.Frame(app, bg="#0E5FB8", height=h or 48)
        alt.pack(side="top", fill="x")
        alt.pack_propagate(False)
        app._alt_topbar = alt
    elif mode == "topbar_nodraw":
        app._topbar._draw = lambda *a, **k: None
    elif mode == "topbar_tuple_fonts":
        # 把命名字体对象换成元组字体（Tcl 侧不用每次查 Font 对象）
        bar = app._topbar
        bar._f_logo = ("Segoe UI", 14, "bold")
        bar._f_brand = ("Segoe UI", 12, "bold")
        bar._f_nav = ("Microsoft YaHei UI", 10)
        bar._f_nav_b = ("Microsoft YaHei UI", 10, "bold")
        bar._f_small = ("Segoe UI", 8)
    elif mode == "topbar_solid_bg":
        # 渐变整块换成一条纯色矩形（item 数 175 → 16）
        import mclite.ui.app as _app_mod
        orig = _app_mod.gradient

        def solid(canvas, w, h, c1, c2, steps=110, tag="grad"):
            canvas.create_rectangle(0, 0, w, h, fill=c1, outline=c1, tags=tag)

        _app_mod.gradient = solid
    elif mode == "topbar_no_gradient":
        # 保留文字和胶囊，只把 160 段渐变换成一条矩形
        bar = app._topbar

        def thin(w=None, h=None):
            bar.delete("all")
            bar.create_rectangle(0, 0, bar.winfo_width(), bar.winfo_height(),
                                 fill="#0E5FB8", outline="")

        bar._draw = thin
    elif mode == "topbar_gradient_only":
        # 只画渐变背景（160 段），不画任何前景
        from mclite.ui import theme as _t
        bar = app._topbar

        def grad_only(*_a, **_k):
            bar.delete("all")
            w, h = bar.winfo_width(), bar.winfo_height()
            _t.gradient(bar, w, h, _t.ACCENT_DARK, _t.ACCENT_HOVER, steps=160, tag="topbg")

        bar._draw = grad_only
    elif mode == "topbar_grad24":
        # 渐变降到 24 段，前景照旧
        from mclite.ui import theme as _t
        bar = app._topbar
        real_bar_draw = _t.__dict__

        def grad24(canvas, w, h, c1, c2, steps=110, tag="grad"):
            _t._orig_gradient(canvas, w, h, c1, c2, steps=24, tag=tag)

        if not hasattr(_t, "_orig_gradient"):
            _t._orig_gradient = _t.gradient
            _t.gradient = grad24
            import mclite.ui.app as _app_mod
            _app_mod.gradient = grad24
    elif mode == "topbar_no_avatar":
        # 前景照画，但不嵌 Avatar 子控件（create_window 会牵动子控件布局）
        import mclite.ui.app as _app_mod
        bar = app._topbar
        _real = bar.create_window

        def skip_window(*a, **k):
            return 0

        bar.create_window = skip_window
    elif mode == "topbar_no_text":
        # 前景照画，只是不写字（字体渲染/度量）
        bar = app._topbar
        _real = bar.create_text
        bar.create_text = lambda *a, **k: 0
    elif mode == "topbar_no_round":
        # 前景照画，但圆角矩形画成普通矩形
        import mclite.ui.app as _app_mod
        import mclite.ui.theme as _t
        orig = _t.round_rect

        def flat(canvas, x0, y0, x1, y1, r, **kw):
            canvas.create_rectangle(x0, y0, x1, y1, **kw)

        _t.round_rect = flat
        _app_mod.round_rect = flat
    elif mode == "topbar_keep_items":
        # 不删旧 item，只叠加（验证「delete 大量 item」是否是成本）
        bar = app._topbar
        _real = bar.delete
        bar.delete = lambda *a, **k: None
    elif mode == "topbar_fg_only":
        # 只画前景（文字/胶囊/按钮），不画渐变
        from mclite.ui import theme as _t
        bar = app._topbar
        orig_gradient = _t.gradient

        def no_grad(canvas, w, h, c1, c2, steps=110, tag="grad"):
            return

        _t.gradient = no_grad
        import mclite.ui.app as _app_mod
        _app_mod.gradient = no_grad
    elif mode == "topbar_few_items":
        # 只画渐变背景，不画文字/按钮
        bar = app._topbar
        from ..mclite.ui import theme as _t  # noqa: F401

        def bg_only(w=None, h=None):
            bar.delete("all")
            bar.create_rectangle(0, 0, bar.winfo_width(), bar.winfo_height(),
                                 fill="#0E5FB8", outline="")

        bar._draw = bg_only
    else:
        raise SystemExit(f"unknown mode {mode}")
    drain(app, 0.4)


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    page_name = sys.argv[2] if len(sys.argv) > 2 else "home"

    from mclite.ui import app as app_mod

    app = app_mod.App()
    app.create_pages()
    drain(app, 1.0)
    app.show_page(page_name)
    drain(app, 0.8)
    page = app._pages[page_name]
    apply_mode(app, page, mode)

    rounds = [drag(app) for _ in range(ROUNDS)]
    mids = sorted(r["mid"] for r in rounds)
    out = {
        "mode": mode,
        "page": page_name,
        "mid": statistics.median(mids),
        "worst_round": max(r["worst"] for r in rounds),
        "over": statistics.median(r["over"] for r in rounds),
        "rounds": [round(m, 1) for m in mids],
        "page_widgets": len(page.winfo_children()),
    }
    print(json.dumps(out, ensure_ascii=False))
    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
