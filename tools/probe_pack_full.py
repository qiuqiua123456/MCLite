"""完整装一个真实整合包（含 mod 下载），用于验证整条链路。

用法：python tools\\probe_pack_full.py ["搜索词"] [mc版本] [游戏目录]
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mclite import modpack, modrinth  # noqa: E402
from mclite.downloader import Downloader, DownloadTask  # noqa: E402


def main() -> int:
    query = sys.argv[1] if len(sys.argv) > 1 else "fabulously optimized"
    mc = sys.argv[2] if len(sys.argv) > 2 else "1.20.1"
    game_dir = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("G:/.minecraft")

    items, _total = modrinth.search(query, mc, "", limit=5, project_type="modpack")
    if not items:
        print("没搜到")
        return 1
    project = items[0]
    vers = modrinth.versions(project.project_id, mc, "")
    if not vers:
        print("没有匹配的游戏版本")
        return 1
    version = vers[0]
    f = modrinth.primary_file(version)
    print(f"{project.title} / {version.name} / {f.filename} {f.size / 1048576:.2f} MB")

    temp = Path(tempfile.gettempdir()) / "MCLite" / "packs"
    temp.mkdir(parents=True, exist_ok=True)
    dest = temp / f.filename
    if not dest.is_file():
        ok, bad = Downloader(threads=4).run(
            [DownloadTask(url=f.url, dest=dest, sha1=f.sha1 or None, size=f.size or None)],
            source="official")
        if not ok or bad:
            print("整合包下载失败")
            return 1
    print(f"整合包就位：{dest} {dest.stat().st_size} B")

    started = time.time()
    last = [0.0]

    def on_log(msg: str) -> None:
        print(f"[{time.time() - started:6.1f}s] {msg}", flush=True)

    def on_progress(p) -> None:
        now = time.time()
        if now - last[0] < 3.0:
            return
        last[0] = now
        print(f"[{now - started:6.1f}s]   {p.done}/{p.total} 文件 "
              f"{p.bytes_done / 1048576:.1f} MB {p.speed / 1048576:.2f} MB/s", flush=True)

    try:
        vid = modpack.install(dest, game_dir, on_log=on_log, progress_cb=on_progress)
    except Exception as exc:                         # noqa: BLE001
        print(f"安装失败：{type(exc).__name__}: {exc}")
        return 1
    print(f"完成：{vid}  用时 {time.time() - started:.1f}s")

    vdir = game_dir / "versions" / vid
    mods = sorted((vdir / "mods").glob("*.jar")) if (vdir / "mods").is_dir() else []
    print(f"mods：{len(mods)} 个，共 {sum(p.stat().st_size for p in mods) / 1048576:.1f} MB")
    print(f"version json：{(vdir / f'{vid}.json').is_file()}")
    print(f"清理：{'已删除' if not shutil.rmtree(vdir, ignore_errors=False) else ''}" if False else "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
