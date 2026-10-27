"""运行时切换主题的验收：先按配置主题启动，再就地切到 light，截图对比。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mclite.ui.app import App          # noqa: E402
from tools.screenshot import capture   # noqa: E402


def pump(app, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        try:
            app.update_idletasks()
            app.update()
        except Exception:                 # noqa: BLE001
            return
        time.sleep(0.02)


def main() -> int:
    out_dir = ROOT / "shots"
    out_dir.mkdir(parents=True, exist_ok=True)

    app = App()
    app.create_pages()
    app.show_page("settings")
    pump(app, 2.0)
    capture(app, out_dir / "th_before.png")

    app.apply_theme("light")
    pump(app, 2.0)
    capture(app, out_dir / "th_light.png")

    from mclite.ui import theme as th
    print("theme =", th.THEME, "BG =", th.BG, "BG_ALT =", th.BG_ALT)
    page = app._pages.get("settings")
    print("app bg =", app.cget("bg"))
    if page is not None:
        print("page bg =", page.cget("bg"))

    # 再切回 pcl，确认可逆
    app.apply_theme("pcl")
    pump(app, 1.5)
    capture(app, out_dir / "th_back.png")
    print("theme =", th.THEME, "BG =", th.BG)
    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
