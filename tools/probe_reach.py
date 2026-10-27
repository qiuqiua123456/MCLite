"""逐个探测加载器相关站点，找出这台机器上真正能通的镜像。"""

from __future__ import annotations

import json
import time
import urllib.request

UA = {"User-Agent": "MCLite/1.0.0"}
TARGETS = [
    ("BMCLAPI forge 列表", "https://bmclapi2.bangbang93.com/forge/minecraft/1.20.1"),
    ("BMCLAPI fabric 列表", "https://bmclapi2.bangbang93.com/fabric-meta/v2/versions/loader/1.20.1"),
    ("BMCLAPI neoforge 列表", "https://bmclapi2.bangbang93.com/neoforge/list/1.20.1"),
    ("Forge maven 元数据", "https://maven.minecraftforge.net/net/minecraftforge/forge/maven-metadata.xml"),
    ("Forge 官网 promos", "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"),
    ("NeoForge maven 元数据", "https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml"),
    ("Fabric meta 官方", "https://meta.fabricmc.net/v2/versions/loader/1.20.1"),
    ("Modrinth API", "https://api.modrinth.com/v2/tag/game_version"),
]

for name, url in TARGETS:
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=12) as r:
            body = r.read()
        print(f"OK   {time.time()-t0:5.2f}s  {len(body):>8} B  {name}")
    except Exception as exc:                              # noqa: BLE001
        print(f"FAIL {time.time()-t0:5.2f}s  {type(exc).__name__}: {str(exc)[:60]}  {name}")
