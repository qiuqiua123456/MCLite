"""在临时目录里真跑一遍 Forge 安装，验证 --mirror 指向 BMCLAPI 能不能装成功。"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

TMP = Path(r"C:\Users\qiu\AppData\Local\Temp\mclite_probe")
SCRATCH = TMP / "mctest"
FORGE_JAR = sorted(TMP.glob("forge-1.20.1-*-installer.jar"))[-1]
JAVA = r"C:\Program Files\Java\jre1.8.0_333\bin\java.exe"
GAME = Path(r"G:\.minecraft")

# 临时游戏目录里只放 1.20.1 本体，让安装器自己去下载它要的东西
vanilla = SCRATCH / "versions" / "1.20.1"
if not vanilla.exists():
    vanilla.mkdir(parents=True)
    for f in (GAME / "versions" / "1.20.1").iterdir():
        if f.is_file():
            shutil.copy2(f, vanilla / f.name)
print("临时目录:", SCRATCH, "| 本体文件:", [p.name for p in vanilla.iterdir()])

# 安装器要求目标目录里有 launcher_profiles.json，否则直接报错退出
prof = SCRATCH / "launcher_profiles.json"
if not prof.exists():
    prof.write_text(json.dumps({"profiles": {}, "settings": {}, "version": 3}), encoding="utf-8")

cmd = [JAVA, "-jar", str(FORGE_JAR), "--installClient", str(SCRATCH),
       "--mirror", "https://bmclapi2.bangbang93.com/maven"]
print("\n执行:", " ".join(cmd))
t0 = time.time()
r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
print(f"rc={r.returncode}  用时 {time.time()-t0:.1f}s")
print("--- stdout 尾部 ---")
print(r.stdout[-2500:])
print("--- stderr 尾部 ---")
print(r.stderr[-1500:])

made = SCRATCH / "versions" / "1.20.1-forge-47.4.27"
print("\n产物目录存在:", made.exists())
if made.exists():
    for p in made.iterdir():
        print("   ", p.name, p.stat().st_size)
