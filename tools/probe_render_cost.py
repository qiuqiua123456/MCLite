"""量 _render_now 本身：销毁+重建 16 行到底花多少，卡在哪一步。"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from smoke_install_filter import fake_versions  # noqa: E402


def pump(app, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.update_idletasks()
        app.update()
        time.sleep(0.01)


def main() -> int:
    import tkinter as tk

    from mclite.ui.app import App
    from mclite.ui import theme

    app = App()
    app.create_pages()
    pump(app, 0.6)
    app.show_page("install")
    pump(app, 0.5)
    page = app._pages["install"]
    page._loading = False
    page._on_manifest(fake_versions())
    pump(app, 0.4)
    inner = page._scroll.inner

    def rebuild_only(tag: str):
        """只做销毁 + 重建，不调 update。"""
        t0 = time.perf_counter()
        for w in inner.winfo_children():
            w.destroy()
        t1 = time.perf_counter()
        n = 0
        for i in range(16):
            head = tk.Frame(inner, bg=theme.BG_ALT)
            head.pack(fill="x")
            tk.Label(head, text=f"组{i}", bg=theme.BG_ALT).pack(side="left")
            tk.Label(head, text=" 1 个", bg=theme.BG_ALT).pack(side="left")
            for j in range(1):
                row = tk.Frame(inner, bg=theme.BG_ALT)
                row.pack(fill="x")
                box = tk.Frame(row, bg=theme.BG_ALT)
                box.pack(side="left", fill="both", expand=True)
                tk.Label(box, text=f"1.{i}.{j}", bg=theme.BG_ALT).pack(fill="x")
                tk.Label(box, text="正式版", bg=theme.BG_ALT).pack(fill="x")
                n += 1
        t2 = time.perf_counter()
        app.update_idletasks()
        t3 = time.perf_counter()
        print(f"  [{tag}] destroy {1000*(t1-t0):6.1f} | create {1000*(t2-t1):6.1f} "
              f"| idle {1000*(t3-t2):6.1f} ms  ({n} 行)")

    print("普通 Frame 重建 16 行：")
    for k in range(4):
        rebuild_only(k)

    print("\n真实 _render_now（含 SelectableRow）：")
    for k in range(4):
        page._filter = None if k % 2 else "release"
        page._render_sig = None
        t0 = time.perf_counter()
        page._render_now()
        t1 = time.perf_counter()
        app.update_idletasks()
        t2 = time.perf_counter()
        app.update()
        t3 = time.perf_counter()
        print(f"  [{k}] _render_now {1000*(t1-t0):7.1f} | idle {1000*(t2-t1):6.1f} "
              f"| update {1000*(t3-t2):7.1f} ms | rows={len(page._rows)}")

    print("\n单单 update()（没有排队渲染）：")
    for k in range(4):
        app.update_idletasks()
        t0 = time.perf_counter()
        app.update()
        print(f"  [{k}] {1000*(time.perf_counter()-t0):7.1f} ms")

    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
