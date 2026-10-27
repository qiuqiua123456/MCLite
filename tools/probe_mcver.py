"""probe：从实例版本 JSON 推断 MC 版本 / 加载器。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mclite import exportpack, instances  # noqa: E402
from mclite.launcher import GameLauncher, list_installed_versions  # noqa: E402

game_dir = Path(r"G:\.minecraft")
for vid in list_installed_versions(game_dir):
    try:
        p = game_dir / "versions" / vid / f"{vid}.json"
        import json
        vjson = json.loads(p.read_text(encoding="utf-8"))
        print(f"{vid:<38} -> {exportpack.detect_dependencies(game_dir, vid, vjson)}")
    except Exception as exc:                          # noqa: BLE001
        print(f"{vid:<38} !! {type(exc).__name__}: {exc}")
