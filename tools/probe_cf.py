"""探测 CurseForge 文件元数据/下载的免 Key 通路。"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
PROJECT = 306612          # Fabric API
FILE = 4563440


def get(url: str, timeout: float = 10) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(4000)
            return f"{r.status} {len(raw)}B {time.time() - t:.2f}s {raw[:220]!r}"
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code} ({time.time() - t:.2f}s)"
    except Exception as e:                              # noqa: BLE001
        return f"ERR {type(e).__name__}: {e} ({time.time() - t:.2f}s)"


CANDIDATES = [
    f"https://cf-api.mcimirror.top/v1/mods/{PROJECT}/files/{FILE}",
    f"https://api.mcimirror.top/v1/mods/{PROJECT}/files/{FILE}",
    f"https://mod.mcimirror.top/curseforge/v1/mods/{PROJECT}/files/{FILE}",
    f"https://curseforge-api.mcimirror.top/v1/mods/{PROJECT}/files/{FILE}",
    f"https://api.cfwidget.com/{PROJECT}",
    f"https://api.curse.tools/v1/cf/mods/{PROJECT}/files/{FILE}",
    f"https://www.curseforge.com/api/v1/mods/{PROJECT}/files?pageIndex=0&pageSize=1",
]

for url in CANDIDATES:
    print(url)
    print("  ->", get(url))
