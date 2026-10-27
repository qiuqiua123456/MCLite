"""直接跑整合包安装（不走 GUI），定位卡在哪一步。

复用上一次测试留下的临时游戏目录（里面已经有完整的 1.20.1 + assets），
只验证「加载器安装 → 解包 overrides → 下载模组 → 生成版本」这几步。
"""

from __future__ import annotations

import sys
import tempfile
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    from mclite import packdetect

    packs = Path(tempfile.gettempdir()) / "MCLite" / "packs"
    cands = sorted(packs.glob("*.mrpack"), key=lambda p: p.stat().st_size)
    if not cands:
        print("没有可用的 .mrpack")
        return 1
    pack = cands[-1]
    print(f"整合包：{pack}（{pack.stat().st_size / 1048576:.1f} MB）")

    game = None
    for d in Path(tempfile.gettempdir()).glob("mclite_packtest_*"):
        g = d / ".minecraft"
        if (g / "assets" / "indexes").exists():
            game = g
            break
    if game is None:
        game = Path(tempfile.mkdtemp(prefix="mclite_packtest2_")) / ".minecraft"
        game.mkdir(parents=True, exist_ok=True)
    print(f"游戏目录：{game}")

    t0 = time.time()

    def log(msg: str) -> None:
        print(f"[{time.time() - t0:6.1f}s] {msg}", flush=True)

    try:
        vid = packdetect.install_any(pack, game, base_version="", on_log=log)
    except Exception:                                # noqa: BLE001
        print("=== 安装抛异常 ===")
        traceback.print_exc()
        return 1

    print(f"=== 装好了：{vid}（{time.time() - t0:.1f}s）===")
    vdir = game / "versions" / vid
    print("版本目录：", vdir)
    for p in sorted(vdir.iterdir()):
        n = (len(list(p.iterdir())) if p.is_dir() else p.stat().st_size)
        print(f"   {p.name}  {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
