"""测 BMCLAPI 的 forge 专用安装器端点，并看它是不是把 URL 改写了。"""

from __future__ import annotations

import io
import json
import time
import urllib.request
import zipfile

UA = {"User-Agent": "MCLite/1.0"}
BM = "https://bmclapi2.bangbang93.com"


def timed(url: str, timeout: int = 25) -> tuple[float, bytes]:
    t0 = time.time()
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return time.time() - t0, r.read()


print("=== BMCLAPI 基础连通性再测 ===")
for u in (f"{BM}/forge/minecraft/1.20.1", f"{BM}/maven/org/spongepowered/mixin/0.8.5/mixin-0.8.5.jar"):
    try:
        dt, body = timed(u)
        print(f"OK   {dt:5.2f}s {len(body):>9} B  {u}")
    except Exception as exc:                             # noqa: BLE001
        print(f"FAIL {type(exc).__name__}: {str(exc)[:40]}  {u}")

print("\n=== forge/download/<build> ===")
for url in (f"{BM}/forge/download/47040027", f"{BM}/forge/version/1.20.1-47.4.28"):
    try:
        dt, body = timed(url, timeout=60)
        print(f"OK   {dt:5.2f}s {len(body):>9} B  iszip={body[:2] == b'PK'}  {url}")
        if body[:2] == b"PK":
            with zipfile.ZipFile(io.BytesIO(body)) as z:
                prof = json.loads(z.read("install_profile.json").decode("utf-8"))
                libs = prof.get("libraries", [])
                print("    库数量:", len(libs))
                for lib in libs[:3]:
                    print("     ", lib.get("name"), "->", ((lib.get("downloads") or {}).get("artifact") or {}).get("url"))
                procs = prof.get("processors", [])
                print("    processors:", len(procs))
                if procs:
                    cp = procs[0].get("classpath", [])
                    print("     第一个 processor classpath[0]:", cp[0] if cp else None)
    except Exception as exc:                             # noqa: BLE001
        print(f"FAIL {type(exc).__name__}: {str(exc)[:50]}  {url}")
