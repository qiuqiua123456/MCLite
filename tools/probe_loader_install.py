"""测试新的「先补库、再跑安装器」流程。用法：probe_loader_install.py <kind> <mc> <ver> <目录>"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mclite import loaders  # noqa: E402
from mclite.java import detect_all, pick_for_version, required_java  # noqa: E402


def _java_for(mc: str) -> str:
    need = required_java({"id": mc}) or 17
    found = detect_all()
    best = pick_for_version(found, need)
    if best is None:
        raise SystemExit(f"没有找到 Java {need}+")
    print(f"使用 Java {best.version} ({best.path})，需要 {need}+")
    return str(best.path)


def main() -> int:
    if len(sys.argv) < 5:
        print(__doc__)
        return 2
    kind, mc, ver, target = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    game_dir = Path(target)
    game_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    java = _java_for(mc)

    def log(msg: str) -> None:
        print(f"[{time.time() - t0:6.1f}s] {msg}", flush=True)

    try:
        vid = loaders.install(kind, mc, ver, game_dir, java, log)
    except Exception as exc:                         # noqa: BLE001
        print(f"失败：{type(exc).__name__}: {exc}")
        return 1
    print(f"成功：{vid}，总用时 {time.time() - t0:.1f}s")
    d = game_dir / "versions" / vid
    print("产物：", [p.name for p in d.iterdir()])
    libs = list((game_dir / "libraries").rglob("*.jar"))
    print(f"libraries: {len(libs)} 个 jar")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
