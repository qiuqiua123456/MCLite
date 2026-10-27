"""把「切筛选」那一帧拆成 set_filter / idle(布局) / update(重绘)，交替多次看谁慢。"""
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
    from mclite.ui.app import App

    app = App()
    app.create_pages()
    pump(app, 0.6)
    app.show_page("install")
    pump(app, 0.5)
    page = app._pages["install"]
    page._loading = False
    page._on_manifest(fake_versions())
    pump(app, 0.4)
    sf = page._scroll

    print("起始 inner:", sf.inner.winfo_width(), "x", sf.inner.winfo_height(),
          "region:", sf._canvas.cget("scrollregion"))

    for i in range(8):
        kind = "release" if i % 2 == 0 else None
        t0 = time.perf_counter()
        page._set_filter(kind)
        t1 = time.perf_counter()
        app.update_idletasks()
        t2 = time.perf_counter()
        app.update()
        t3 = time.perf_counter()
        print(f"[{i}] filter={str(kind):8s} set={1000*(t1-t0):6.1f} "
              f"idle={1000*(t2-t1):7.1f} draw={1000*(t3-t2):7.1f} ms "
              f"| rows={len(page._rows):2d} inner={sf.inner.winfo_height()} "
              f"region={sf._canvas.cget('scrollregion')}")

    # 再单独测：不换筛选，只让 ScrollFrame 重新同步一次宽度
    print("\n单独触发 ScrollFrame 宽度同步：")
    for _ in range(3):
        sf._win_w = 1                     # 强制认为宽度变了
        sf._flush_width()
        t0 = time.perf_counter()
        app.update_idletasks()
        app.update()
        print(f"  flush_width 后一帧 {(time.perf_counter()-t0)*1000:7.1f} ms")

    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
