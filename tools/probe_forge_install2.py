"""Forge 安装第二轮：不用 --mirror，靠 Java 自己的 IPv4 + Java UA 直连。"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

TMP = Path(r"C:\Users\qiu\AppData\Local\Temp\mclite_probe")
SCRATCH = TMP / "mctest2"
FORGE_JAR = sorted(TMP.glob("forge-1.20.1-*-installer.jar"))[-1]
JAVA = r"C:\Program Files\Java\jre1.8.0_333\bin\java.exe"
GAME = Path(r"G:\.minecraft")

vanilla = SCRATCH / "versions" / "1.20.1"
if not vanilla.exists():
    vanilla.mkdir(parents=True)
    for f in (GAME / "versions" / "1.20.1").iterdir():
        if f.is_file():
            shutil.copy2(f, vanilla / f.name)

(SCRATCH / "launcher_profiles.json").write_text(
    json.dumps({"profiles": {}, "settings": {}, "version": 3}), encoding="utf-8")

cmd = [JAVA, "-jar", str(FORGE_JAR), "--installClient", str(SCRATCH)]
print("执行:", " ".join(cmd))
t0 = time.time()
r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
print(f"rc={r.returncode}  用时 {time.time()-t0:.1f}s")
tail = [ln for ln in r.stdout.splitlines() if ln.strip()][-14:]
print("--- stdout 尾部 ---")
print("\n".join(tail))

made = SCRATCH / "versions" / "1.20.1-forge-47.4.27"
print("\n产物目录:", made.exists())
if made.exists():
    for p in made.iterdir():
        print("   ", p.name, p.stat().st_size)
    vj = json.loads((made / "1.20.1-forge-47.4.27.json").read_text(encoding="utf-8"))
    print("   id:", vj.get("id"), "| inheritsFrom:", vj.get("inheritsFrom"),
          "| libs:", len(vj.get("libraries", [])), "| mainClass:", vj.get("mainClass"))
    urls = {lib.get("downloads", {}).get("artifact", {}).get("url", "")[:40]
            for lib in vj.get("libraries", [])}
    print("   URL 前缀样本:", sorted(u for u in urls if u)[:4])
