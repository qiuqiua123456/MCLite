"""把 Forge 1.20.1 安装器拉下来，看它内部长什么样、跑起来需要哪些 URL。"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

TMP = Path(r"C:\Users\qiu\AppData\Local\Temp\mclite_probe")
TMP.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "MCLite/1.0.0"}


def get(url: str, timeout: int = 30) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


lst = json.loads(get("https://bmclapi2.bangbang93.com/forge/minecraft/1.20.1"))
vers = [d["version"] for d in lst]
print("BMCLAPI forge 1.20.1 共", len(vers), "个，最新:", vers[-1])

fv = vers[-1]
jar = TMP / f"forge-1.20.1-{fv}-installer.jar"
if not jar.exists():
    url = f"https://bmclapi2.bangbang93.com/maven/net/minecraftforge/forge/1.20.1-{fv}/forge-1.20.1-{fv}-installer.jar"
    print("下载", url)
    data = get(url, timeout=180)
    jar.write_bytes(data)
print("安装器:", jar, jar.stat().st_size, "B")

with zipfile.ZipFile(jar) as z:
    names = z.namelist()
    print("\n里面这几个文件值得看:", [n for n in names if n.endswith(".json") or "MANIFEST" in n][:12])
    prof = json.loads(z.read("install_profile.json").decode("utf-8"))
    print("\ninstall_profile 顶层键:", list(prof.keys()))
    print("spec:", prof.get("spec"))
    print("version:", prof.get("version"), "| minecraft:", prof.get("minecraft"))
    libs = prof.get("libraries", [])
    print("libraries:", len(libs))
    for lib in libs[:4]:
        print("   ", lib.get("name"), "->", (lib.get("downloads") or {}).get("artifact", {}).get("url"))
    e404 = [l for l in libs if not ((l.get("downloads") or {}).get("artifact") or {}).get("url")]
    print("没有 url 的库:", len(e404))
    procs = prof.get("processors", [])
    print("processors:", len(procs))
    for p in procs:
        print("    jar:", p.get("jar"), "| classpath:", len(p.get("classpath", [])), "| outputs:", p.get("outputs"))
    print("data 键:", list((prof.get("data") or {}).keys()))
    # 版本 json
    vj_name = prof.get("json") or ""
    print("\nversion.json entry:", vj_name)
    if vj_name and vj_name in names:
        vj = json.loads(z.read(vj_name).decode("utf-8"))
        print("version.json id:", vj.get("id"), "| inheritsFrom:", vj.get("inheritsFrom"),
              "| libs:", len(vj.get("libraries", [])), "| mainClass:", vj.get("mainClass"))

print("\n=== 跑 --help ===")
java = r"C:\Program Files\Java\jre1.8.0_333\bin\java.exe"
r = subprocess.run([java, "-jar", str(jar), "--help"], capture_output=True, text=True, timeout=120)
print("rc:", r.returncode)
print(r.stdout[-1500:])
print(r.stderr[-800:])
