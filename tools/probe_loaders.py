"""探测 Forge / NeoForge 安装器命令行参数，并确认 Fabric 元数据接口。"""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

TMP = Path(r"C:\Users\qiu\AppData\Local\Temp\mclite_probe")
TMP.mkdir(parents=True, exist_ok=True)

UA = {"User-Agent": "MCLite/1.0.0"}


def get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def text(url: str) -> str:
    return get(url).decode("utf-8", "replace")


def maven_versions(meta_url: str) -> list[str]:
    xml = text(meta_url)
    return re.findall(r"<version>([^<]+)</version>", xml)


print("=== Forge 1.20.1 版本（取后 5 个）===")
fv = [v for v in maven_versions("https://maven.minecraftforge.net/net/minecraftforge/forge/maven-metadata.xml")
      if v.startswith("1.20.1-")]
print(len(fv), fv[-5:])

print("\n=== NeoForge maven 版本（取后 5 个）===")
try:
    nv = maven_versions("https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml")
    print(len(nv), nv[-5:])
except Exception as exc:                                  # noqa: BLE001
    print("FAIL", type(exc).__name__, exc)

print("\n=== NeoForge 1.20.1（旧 artifact forge）===")
try:
    ov = [v for v in maven_versions("https://maven.neoforged.net/releases/net/neoforged/forge/maven-metadata.xml")
          if v.startswith("1.20.1-")]
    print(len(ov), ov[-5:])
except Exception as exc:                                  # noqa: BLE001
    print("FAIL", type(exc).__name__, exc)

print("\n=== BMCLAPI Forge 列表 ===")
try:
    data = json.loads(get("https://bmclapi2.bangbang93.com/forge/minecraft/1.20.1"))
    print(len(data), [d.get("version") for d in data][-5:])
except Exception as exc:                                  # noqa: BLE001
    print("FAIL", type(exc).__name__, exc)

print("\n=== Fabric loader 列表 ===")
try:
    data = json.loads(get("https://meta.fabricmc.net/v2/versions/loader/1.20.1"))
    print(len(data), [(d["loader"]["version"], d["loader"]["stable"]) for d in data][:5])
except Exception as exc:                                  # noqa: BLE001
    print("FAIL", type(exc).__name__, exc)
