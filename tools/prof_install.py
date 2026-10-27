"""定位切到下载页为什么慢（稳态 ~390ms）。

只 profile 来回切换，输出累计耗时最高的函数。
"""

from __future__ import annotations

import cProfile
import io
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

    # 预热一轮
    for key in ("install", "settings", "home"):
        app.show_page(key)
        app.update_idletasks()
        app.update()

    prof = cProfile.Profile()
    prof.enable()
    for _ in range(2):
        for key in ("install", "settings", "home", "install"):
            t = time.perf_counter()
            app.show_page(key)
            app.update_idletasks()
            app.update()
            ms = (time.perf_counter() - t) * 1000
            print(f"  {key:<9} {ms:6.1f} ms")
    prof.disable()

    buf = io.StringIO()
    pstats.Stats(prof, stream=buf).sort_stats("cumulative").print_stats(18)
    text = buf.getvalue()
    print("\n".join(text.splitlines()[:40]))
    app.destroy()


if __name__ == "__main__":
    main()
