"""检查 BMCLAPI maven 镜像是否覆盖 Forge 需要的那些产物。"""

from __future__ import annotations

import time
import urllib.request

BASE = "https://bmclapi2.bangbang93.com/maven/"
PATHS = [
    "net/minecraftforge/accesstransformers/8.0.4/accesstransformers-8.0.4.jar",
    "org/spongepowered/mixin/0.8.5/mixin-0.8.5.jar",
    "org/jline/jline-reader/3.12.1/jline-reader-3.12.1.jar",
    "de/oceanlabs/mcp/mcp_config/1.20.1-20230612.114412/mcp_config-1.20.1-20230612.114412.zip",
    "net/minecraftforge/JarJarSelector/0.3.19/JarJarSelector-0.3.19.jar",
    "cpw/mods/bootstraplauncher/1.1.2/bootstraplauncher-1.1.2.jar",
    "net/minecraftforge/installertools/1.4.1/installertools-1.4.1-fat.jar",
    "net/minecraftforge/binarypatcher/1.1.1/binarypatcher-1.1.1-fat.jar",
]

for p in PATHS:
    t0 = time.time()
    try:
        req = urllib.request.Request(BASE + p, headers={"User-Agent": "MCLite/1.0"}, method="HEAD")
        with urllib.request.urlopen(req, timeout=20) as r:
            print(f"OK   {r.status}  {r.headers.get('Content-Length'):>10}  {time.time()-t0:4.1f}s  {p}")
    except Exception as exc:                             # noqa: BLE001
        print(f"FAIL {type(exc).__name__}: {str(exc)[:40]:<40} {time.time()-t0:4.1f}s  {p}")
