"""复现 time_switch 里 home 的偶发尖峰，看看到底是哪一步慢。"""

from __future__ import annotations

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

    keys = ["install", "settings", "home"]
    for rnd in range(4):
        for key in keys:
            t = time.perf_counter()
            app.show_page(key)
            t_show = (time.perf_counter() - t) * 1000
            t = time.perf_counter()
            app.update_idletasks()
            t_idle = (time.perf_counter() - t) * 1000
            t = time.perf_counter()
            app.update()
            t_upd = (time.perf_counter() - t) * 1000
            print(f"r{rnd} {key:<9} show={t_show:7.1f} idle={t_idle:7.1f} "
                  f"update={t_upd:7.1f}  total={t_show + t_idle + t_upd:7.1f}")

    app.destroy()


if __name__ == "__main__":
    main()
