"""命令行安装测试：python tools/install_test.py <版本号> [游戏目录]"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mclite.downloader import fetch_json, human_size, human_speed
from mclite.installer import Installer
from mclite.versionmeta import VERSION_MANIFEST, parse_manifest


def main() -> int:
    vid = sys.argv[1] if len(sys.argv) > 1 else "1.20.1"
    game_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(r"G:\.minecraft")
    source = sys.argv[3] if len(sys.argv) > 3 else "official"

    print(f"目标版本 {vid}  →  {game_dir}  源={source}")
    t0 = time.time()
    manifest = fetch_json(VERSION_MANIFEST, source=source)
    versions = {v.id: v for v in parse_manifest(manifest)}
    if vid not in versions:
        print("清单里没有这个版本")
        return 1
    v = versions[vid]

    inst = Installer(game_dir, source=source, threads=16,
                     log=lambda m: print("  [log]", m))

    last = [0.0]

    def on_progress(p):
        now = time.time()
        if now - last[0] < 1.0:
            return
        last[0] = now
        pct, cur, speed = p.snapshot()
        print(f"  {pct * 100:5.1f}%  {p.done_files}/{p.total_files}  "
              f"{human_size(p.done_bytes)}/{human_size(p.total_bytes)}  "
              f"{human_speed(speed)}  {cur}", flush=True)

    ok, msg = inst.install(vid, v.url, progress_cb=on_progress)
    print(f"结果: ok={ok} msg={msg}  用时 {time.time() - t0:.1f}s")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
