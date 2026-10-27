"""真实 app 的拖动卡顿逐层剥离（每档独立进程，避免同进程漂移）。

合成外壳（顶栏渐变 + 左侧栏 + 240 行）拖动只要 6.7ms，真实 app 却要 80ms，
说明不是控件数量的问题，是某个具体结构。这个脚本一档一档剥。

用法：python tools/probe_real_bisect.py <mode>
mode: baseline | no_frameless | no_dwm | no_hero | no_scroll | no_canvas_widgets
      | shell_only | page_blank
"""
from __future__ import annotations

import json
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


def make_app(mode: str):
    import mclite.ui.app as app_mod

    if mode == "no_frameless":
        from mclite.ui import frameless

        frameless.apply = lambda root: False

    if mode == "no_dwm":
        import mclite.ui.frameless as fl

        fl._round_corners = lambda hwnd: None

    app = app_mod.App()
    app.create_pages()
    app.update()
    app.show_page("home")
    app.update()
    return app


def mutate(app, mode: str) -> str:
    page = app._pages["home"]

    if mode == "no_hero":
        # 把 hero 贴图 canvas 从布局里摘掉
        n = 0
        for w in list(page.winfo_children()):
            for c in list(w.winfo_children()):
                if c.winfo_class() == "Canvas" and c.winfo_height() > 100:
                    c.pack_forget()
                    n += 1
        return f"摘掉 {n} 个大 canvas"

    if mode == "shell_only":
        for key, p in app._pages.items():
            p.place_forget()
        return "所有页面 place_forget（只剩顶栏+侧栏）"

    if mode == "page_blank":
        for w in list(page.winfo_children()):
            w.pack_forget()
        return "home 页面内容全部 pack_forget"

    if mode == "no_canvas_widgets":
        # 把页面里所有 Canvas 子类控件（FlatButton/Slider 等）pack_forget
        from mclite.ui.theme import FlatButton, Slider

        n = 0

        def walk(w):
            nonlocal n
            for c in list(w.winfo_children()):
                if isinstance(c, (FlatButton, Slider)):
                    try:
                        if c.winfo_manager():
                            c.pack_forget() if c.winfo_manager() == "pack" else c.grid_forget()
                            n += 1
                    except Exception:              # noqa: BLE001
                        pass
                walk(c)

        walk(page)
        return f"摘掉 {n} 个 Canvas 控件"

    return "未改动"


def measure(app) -> tuple[float, float]:
    """心跳法：改宽度写进心跳回调里，`after` 重新计时放在它之后。

    顺序很要紧——先记「这次心跳迟到了多少」，再改宽度，最后重新排下一次心跳。
    这样下一次的间隔天然包含「改宽度 → 系统重排重绘」的成本。反过来让外部
    driver 循环按 16ms 节奏改宽度，driver 的 sleep 会把抖动吸收掉，量出来恒为
    16ms（假数字）。
    """
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


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    app = make_app(mode)
    note = mutate(app, mode)
    app.update()
    time.sleep(0.3)

    # 只测一轮。同一进程里第二轮数字必然暴涨（实测 15.0 → 114.8 → 152.4），
    # 那是 Windows/Tk 内部状态累积，不是代码成本。要比较就每档起独立进程。
    mid, worst = measure(app)
    app.destroy()

    print("{" + f'"mode": "{mode}", "note": "{note}", "mid": {mid:.1f}, "worst": {worst:.1f}' + "}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
