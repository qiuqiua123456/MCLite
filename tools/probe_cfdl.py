"""验证 CurseForge 免 Key 解析 + CDN 直链下载。"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mclite import curseforge                      # noqa: E402
from mclite.downloader import human_size           # noqa: E402

PROJECT = 306612          # Fabric API
FILE = 8784061            # [1.20.1] Fabric API 0.92.12+1.20.1（cfwidget 的 latest）


def main() -> None:
    t = time.time()
    name = curseforge.file_name(PROJECT, FILE)
    print(f"file_name -> {name!r}  ({time.time() - t:.2f}s)")
    if not name:
        print("拿不到文件名，退出")
        return
    print("cdn:", curseforge.cdn_urls(FILE, name))

    files = [{"projectID": PROJECT, "fileID": FILE, "required": True}]
    items, missing = curseforge.resolve(files, on_log=print)
    print("resolve:", len(items), "missing:", missing)

    out = Path(tempfile.mkdtemp(prefix="mclite-cfdl-"))
    ok, failed = curseforge.download_mods(items, out, on_log=print)
    print("download:", ok, "failed:", len(failed))
    for path in sorted(out.iterdir()):
        print("  ", path.name, human_size(path.stat().st_size))
    print("summary:", curseforge.summary(ok, missing))
    import shutil
    shutil.rmtree(out, ignore_errors=True)


if __name__ == "__main__":
    main()
