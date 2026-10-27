"""造一个最小 .mrpack 并真的装一遍，验证整合包链路。

用法：python tools\\probe_pack.py [游戏目录]
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mclite import modpack  # noqa: E402

NAME = "连通性测试包"


def build_pack() -> Path:
    tmp = Path(tempfile.gettempdir()) / "mclite_probe_pack"
    tmp.mkdir(parents=True, exist_ok=True)
    path = tmp / "connectivity.mrpack"
    index = {
        "formatVersion": 1,
        "game": "minecraft",
        "versionId": "1.0.0",
        "name": NAME,
        "summary": "只用来看链路通不通，没有任何外部下载",
        "files": [],
        "dependencies": {"minecraft": "1.20.1"},
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("modrinth.index.json", json.dumps(index, ensure_ascii=False, indent=2))
        zf.writestr("overrides/config/mclite-test.txt", "hello from modpack\n")
        zf.writestr("client-overrides/options.txt", "lang:zh_cn\n")
    return path


def main() -> int:
    game_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r"G:\.minecraft")
    pack = build_pack()
    print(f"整合包：{pack}  {pack.stat().st_size} B")

    idx = modpack.read_index(pack)
    print(f"解析：{idx.label}  mc={idx.mc_version} loader={idx.loader_kind or '-'} "
          f"files={idx.file_count}")

    started = time.time()
    try:
        vid = modpack.install(pack, game_dir, on_log=lambda m: print("   ", m))
    except Exception as exc:                         # noqa: BLE001
        print(f"安装失败：{type(exc).__name__}: {exc}")
        return 1
    print(f"装成版本：{vid}  用时 {time.time() - started:.1f}s")

    vdir = game_dir / "versions" / vid
    for rel in ("config/mclite-test.txt", "options.txt", f"{vid}.json"):
        p = vdir / rel
        print(f"   {'✔' if p.is_file() else '✘'} {rel}")
    print(f"   is_pack={modpack.is_pack(game_dir, vid)}")
    print(f"   list_packs={modpack.list_packs(game_dir)}")

    # 清理
    shutil.rmtree(vdir, ignore_errors=True)
    print("已清理测试版本目录")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
