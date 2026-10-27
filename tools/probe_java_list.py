"""列出 Java 运行时清单里 windows-x64 的全部组件（含版本与总体积）。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mclite import javaauto  # noqa: E402
from mclite.downloader import fetch_json  # noqa: E402


def main() -> int:
    manifest = fetch_json(javaauto.RUNTIME_MANIFEST, timeout=30)
    table = manifest.get("windows-x64") or {}
    for name, entries in sorted(table.items()):
        entry = entries[0] if entries else {}
        ver = (entry.get("version") or {})
        avail = (entry.get("availability") or {}).get("group")
        print(f"{name:24} {str(ver.get('name')):12} major={javaauto._major_of(ver.get('name')):<3} "
              f"group={avail} released={ver.get('released')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
