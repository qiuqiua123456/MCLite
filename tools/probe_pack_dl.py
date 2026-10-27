"""从 Modrinth 下载一个真实的 .mrpack 并解析（不安装）。

用法：python tools\\probe_pack_dl.py ["搜索词"]
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mclite import modpack, modrinth  # noqa: E402


def main() -> int:
    query = sys.argv[1] if len(sys.argv) > 1 else "fabulously optimized"
    started = time.time()
    items, total = modrinth.search(query, "", "", limit=5, project_type="modpack")
    print(f"搜索 {query!r}：{total} 个结果，{time.time() - started:.2f}s")
    if not items:
        print("没搜到")
        return 1
    project = items[0]
    print(f"选中：{project.title}  ({project.project_id})")

    vers = modrinth.versions(project.project_id, "", "")
    print(f"版本 {len(vers)} 个，最新：{vers[0].name}")
    file = modrinth.primary_file(vers[0])
    if file is None:
        print("没有可下载文件")
        return 1
    print(f"文件：{file.filename}  {file.size / 1048576:.2f} MB")

    dest = Path(tempfile.gettempdir()) / "mclite_packtest"
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / (file.filename or "pack.mrpack")
    t = time.time()
    from mclite.downloader import Downloader, DownloadTask
    task = DownloadTask(url=file.url, dest=target, sha1=file.sha1 or None,
                        size=file.size or None)
    ok, bad = Downloader(threads=4).run([task], source="official")
    print(f"下载 {'ok' if ok and not bad else 'FAIL'} {target.stat().st_size} B，"
          f"用时 {time.time() - t:.1f}s")

    idx = modpack.read_index(target)
    print(f"解析：{idx.label}  mc={idx.mc_version} loader={idx.loader_kind} "
          f"{idx.loader_version}  files={idx.file_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
