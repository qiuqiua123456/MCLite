"""单独验证：按 SHA1 把 Forge install_profile 里的库补齐要多久、成功率多少。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mclite.loaders import _seed_installer_libs  # noqa: E402


def main() -> int:
    if len(sys.argv) < 3:
        print("用法: probe_seed.py <installer.jar> <目标目录>")
        return 2
    jar = Path(sys.argv[1])
    target = Path(sys.argv[2])
    target.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    def log(msg: str) -> None:
        print(f"[{time.time() - t0:6.1f}s] {msg}", flush=True)

    _seed_installer_libs(jar, target, log, None)
    jars = list((target / "libraries").rglob("*.jar"))
    total = sum(p.stat().st_size for p in jars)
    log(f"完成：{len(jars)} 个 jar，合计 {total / 1024 / 1024:.1f} MB，用时 {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
