"""抓「松手对齐」里那些 800–900ms 的大帧到底卡在哪。

现象：`smoke_resize.py` 的 settle 偶尔整轮变成 ~830/850/900 ms，而单帧
`update_idletasks` 只有 7 ms。800–900 这个数量级很像某个定时任务或后台线程
（皮肤头像加载、日志 flush）在抢 GIL。这里在出现大帧时打印：
  1. 当时所有 Tk after 任务
  2. 所有 Python 线程的当前调用栈
  3. 大帧里各阶段的耗时

用法：python tools/probe_settle_spike.py <page> <rounds>
"""

from __future__ import annotations

import sys
import threading
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SPIKE_MS = 200.0


def dump(app, label: str) -> None:
    print(f"\n--- {label} ---")
    try:
        jobs = app.tk.call("after", "info")
        print(f"after 任务 {len(jobs)} 个: {jobs}")
    except Exception as exc:                      # noqa: BLE001
        print("after info 失败:", exc)
    frames = sys._current_frames()
    for t in threading.enumerate():
        if t is threading.main_thread():
            continue
        fr = frames.get(t.ident)
        print(f"线程 {t.name} alive={t.is_alive()}")
        if fr is not None:
            print("".join(traceback.format_stack(fr)[-4:]))


def main() -> None:
    from mclite.ui.app import App

    page_name = sys.argv[1] if len(sys.argv) > 1 else "install"
    rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 8

    app = App()
    app.create_pages()
    try:
        app._pages["install"].load_manifest = lambda *a, **k: None
    except (KeyError, AttributeError):
        pass
    end = time.time() + 1.0
    while time.time() < end:
        app.update()
        time.sleep(0.01)
    page = app._pages[page_name]
    app.show_page(page_name)
    end = time.time() + 0.5
    while time.time() < end:
        app.update()
        time.sleep(0.01)

    for i in range(rounds):
        app.geometry("1160x724")
        app.update_idletasks()
        app.update()
        end = time.time() + 0.3
        while time.time() < end:
            app.update()
            time.sleep(0.01)

        app.geometry("1290x724")
        t0 = time.perf_counter()
        t = time.perf_counter()
        app.update_idletasks()
        idle = (time.perf_counter() - t) * 1000.0
        t = time.perf_counter()
        app.update()
        first = (time.perf_counter() - t) * 1000.0
        frames = []
        while time.perf_counter() - t0 < 3.0:
            f0 = time.perf_counter()
            app.update()
            dt = (time.perf_counter() - f0) * 1000.0
            frames.append(dt)
            if dt > SPIKE_MS:
                dump(app, f"[{i}] 大帧 {dt:.0f} ms")
            if abs(page.winfo_width() - app._container.winfo_width()) <= 2:
                break
            time.sleep(0.004)
        total = (time.perf_counter() - t0) * 1000.0
        print(f"[{i}] 总 {total:6.1f} | idle {idle:5.1f} | 首帧 update {first:6.1f} | "
              f"后续帧 {[round(f) for f in frames]}")
    app.destroy()


if __name__ == "__main__":
    main()
