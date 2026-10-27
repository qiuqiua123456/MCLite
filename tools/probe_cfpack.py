"""造一个 CurseForge 格式整合包，跑通「识别 → 装加载器 → 解覆盖 → 下模组」。"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mclite import packdetect                       # noqa: E402
from mclite.launcher import list_installed_versions  # noqa: E402

GAME = Path("G:/.minecraft")
NAME = "CF自动下载测试"


def build_zip(dest: Path) -> Path:
    manifest = {
        "minecraft": {
            "version": "1.20.1",
            "modLoaders": [{"id": "fabric-0.19.5", "primary": True}],
        },
        "manifestType": "minecraftModpack",
        "manifestVersion": 1,
        "name": NAME,
        "version": "1.0.0",
        "author": "probe",
        "files": [
            {"projectID": 306612, "fileID": 8784061, "required": True},    # Fabric API
            {"projectID": 999999999, "fileID": 1234567, "required": True},  # 故意坏的
        ],
        "overrides": "overrides",
    }
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        zf.writestr("overrides/config/probe-cf.txt", "hello from cf pack\n")
    return dest


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="mclite-cfpack-"))
    zpath = build_zip(tmp / "cfpack.zip")
    print("测试包:", zpath, zpath.stat().st_size, "B")

    info = packdetect.detect(zpath)
    print(f"识别: {info.label} / {info.name} / mc={info.mc_version} / "
          f"loader={info.loader_kind} {info.loader_version} / files={len(info.cf_files)}")
    print("notes:", info.notes)

    t = time.time()
    vid = packdetect.install_any(zpath, GAME, on_log=lambda m: print("  ", m))
    print(f"安装完成: {vid}  用时 {time.time() - t:.1f}s")

    vdir = GAME / "versions" / vid
    mods = sorted((vdir / "mods").glob("*.jar")) if (vdir / "mods").exists() else []
    print("mods:", [(p.name, p.stat().st_size) for p in mods])
    print("overrides:", (vdir / "config" / "probe-cf.txt").exists())
    print("在版本列表里:", vid in list_installed_versions(GAME))

    # 清理
    if vdir.exists():
        shutil.rmtree(vdir, ignore_errors=True)
        print("已删除测试实例", vdir)
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
