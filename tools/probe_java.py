"""检查 Java 自动下载的清单解析（不真下文件）。

用法：python tools\\probe_java.py [大版本号 ...]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mclite import javaauto  # noqa: E402
from mclite.downloader import fetch_json  # noqa: E402


def main() -> int:
    majors = [int(x) for x in sys.argv[1:]] or [8, 17, 21, 25]
    started = time.time()
    manifest = fetch_json(javaauto.RUNTIME_MANIFEST, timeout=30)
    print(f"清单 {time.time() - started:.2f}s  {javaauto.manifest_summary(manifest)}")

    for major in majors:
        try:
            comp, entry = javaauto.pick_component(manifest, major)
        except Exception as exc:                     # noqa: BLE001
            print(f"  Java {major:2}  FAIL {exc}")
            continue
        ver = (entry.get("version") or {}).get("name")
        size = entry.get("size") or 0
        print(f"  Java {major:2}+ -> {comp:22} {ver:18} {size / 1048576:6.1f} MB")

    game_dir = Path(sys.argv[0]).parent and Path("G:/.minecraft")
    print(f"已下载的运行时：{javaauto.installed_runtimes(game_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
