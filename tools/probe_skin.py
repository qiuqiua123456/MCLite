"""探测内置皮肤站的 API 根是否可达（顺便看返回的 serverName）。"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mclite import skin_sites  # noqa: E402


def main() -> int:
    for site in skin_sites.SITES:
        started = time.time()
        try:
            req = urllib.request.Request(
                site.api, headers={"User-Agent": "MCLite/1.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
            meta = data.get("meta") or {}
            name = meta.get("serverName") or "?"
            print(f"{site.name:16} OK   {time.time() - started:5.2f}s  serverName={name}")
        except Exception as exc:                     # noqa: BLE001
            print(f"{site.name:16} FAIL {time.time() - started:5.2f}s  "
                  f"{type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
