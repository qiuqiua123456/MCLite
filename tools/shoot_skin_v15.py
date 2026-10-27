"""截图第三方皮肤站登录弹窗（验证「不自动跳浏览器 + 打开认证页面按钮」）。"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("MCLITE_NO_BROWSER", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mclite import skin_sites                                   # noqa: E402
from mclite.config import Config                                # noqa: E402
from mclite.ui.app import App                                   # noqa: E402
from mclite.ui.skin_dialog import SkinLoginDialog               # noqa: E402
from tools.test_exe import capture_window                       # noqa: E402

SHOTS = Path(__file__).resolve().parent.parent / "shots"


def pump(app, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.03)


def main() -> None:
    for site in skin_sites.SITES:
        print(f"{site.id:10s} {site.name:12s} api={site.api}")

    cfg = Config()
    app = App()
    app.create_pages()
    pump(app, 0.6)

    dlg = SkinLoginDialog(app, on_done=lambda _a: None)
    dlg.grab_set()
    pump(app, 1.2)

    # 切到 MUA 看认证页面提示
    mua = skin_sites.SITE_BY_ID["mua"]
    dlg._pick_site(mua)
    pump(app, 0.5)

    SHOTS.mkdir(exist_ok=True)
    out = SHOTS / "skin_login_v15.png"
    img = capture_window(dlg.winfo_id())
    img.save(out)
    print("saved:", out, img.size)
    print("page label:", dlg._page_label.cget("text").replace("\n", " | "))
    print("site:", dlg._site.id, dlg._site.auth_url)

    dlg.destroy()
    app.destroy()


if __name__ == "__main__":
    main()
