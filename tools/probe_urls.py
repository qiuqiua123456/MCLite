"""探测皮肤站衣柜 / Mojang 换肤页 / CurseForge 下载解析是否可用。"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"


def probe(url: str, timeout: float = 10, method: str = "GET") -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA}, method=method)
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = b"" if method == "HEAD" else r.read(120)
            ctype = r.headers.get("Content-Type", "")
            extra = ""
            if method != "HEAD" and "json" in ctype:
                try:
                    extra = " " + json.dumps(r.read(0) or {}, ensure_ascii=False)[:80]
                except Exception:                       # noqa: BLE001
                    extra = ""
            return f"{r.status} {ctype} {len(body)}B {time.time() - t:.2f}s{extra}"
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code} ({time.time() - t:.2f}s) loc={e.headers.get('Location')}"
    except Exception as e:                              # noqa: BLE001
        return f"ERR {type(e).__name__}: {e} ({time.time() - t:.2f}s)"


URLS = [
    "https://littleskin.cn/user/closet",
    "https://littleskin.cn/closet",
    "https://littleskin.cn/user",
    "https://skin.mualliance.cn/user/closet",
    "https://skin.mualliance.cn/auth/login",
    "https://www.minecraft.net/zh-hans/msaprofile/mygames/editskin",
    "https://www.minecraft.net/en-us/msaprofile/mygames/editskin",
    "https://edge.forgecdn.net/files/4563/440/fabric-api-0.92.0%2B1.20.1.jar",
    "https://mediafilez.forgecdn.net/files/4563/440/fabric-api-0.92.0%2B1.20.1.jar",
    "https://www.curseforge.com/api/v1/mods/306612/files/4563440/download",
    "https://api.curseforge.com/v1/mods/306612/files/4563440",
]

for u in URLS:
    print(u)
    print("  ->", probe(u))
