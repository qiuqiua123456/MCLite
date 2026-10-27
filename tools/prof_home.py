"""稳态切到 home 为什么慢？单独 cProfile 找热点。"""

from __future__ import annotations

import cProfile
import pstats
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mclite.ui.app import App  # noqa: E402


def main() -> None:
    app = App()
    app.create_pages()
    for _ in range(3):
        app.update_idletasks()
        app.update()

    # 预热：先来回切几轮
    for _ in range(3):
        for key in ("install", "settings", "home"):
            app.show_page(key)
            app.update_idletasks()
            app.update()

    prof = cProfile.Profile()
    prof.enable()
    for _ in range(6):
        for key in ("install", "settings", "home"):
            app.show_page(key)
            app.update_idletasks()
            app.update()
    prof.disable()

    print("— 单独计时 home —")
    for _ in range(5):
        app.show_page("install")
        app.update()
        t = time.perf_counter()
        app.show_page("home")
        app.update_idletasks()
        app.update()
        print(f"  home = {(time.perf_counter() - t) * 1000:6.1f} ms")

    stats = pstats.Stats(prof)
    stats.sort_stats("cumulative")
    print("\n— top 22 by cumulative —")
    stats.print_stats(22)

    app.destroy()


if __name__ == "__main__":
    main()
