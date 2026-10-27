"""定位「拉伸窗口很卡」的具体开销：对一次窗口缩放做 cProfile。"""

from __future__ import annotations

import cProfile
import io
import pstats
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def pump(app, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.update_idletasks()
        app.update()
        time.sleep(0.005)


def main() -> int:
    from mclite.ui.app import App

    page = sys.argv[1] if len(sys.argv) > 1 else "settings"
    app = App()
    app.create_pages()
    pump(app, 0.8)
    app.show_page(page)
    pump(app, 0.6)

    widths = [1240, 1080, 1400, 1160, 1320]

    def run() -> None:
        for w in widths:
            app.geometry(f"{w}x724")
            app.update_idletasks()
            app.update()
            time.sleep(0.02)

    import ctypes
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:                            # noqa: BLE001
            pass

    run()                                        # 预热
    pr = cProfile.Profile()
    pr.enable()
    run()
    pr.disable()
    s = io.StringIO()
    st = pstats.Stats(pr, stream=s).sort_stats("cumulative")
    st.print_stats(28)
    print(s.getvalue())
    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
