"""第三轮：安装器多轮重试（断点续传式），看能不能在几十秒~几分钟内收敛成功。"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

S = Path(r"C:\Users\qiu\AppData\Local\Temp\mclite_probe\mctest3")
JAVA = r"C:\Program Files\Java\jre1.8.0_333\bin\java.exe"
MIRROR = "https://bmclapi2.bangbang93.com/maven/"


def lib_count() -> int:
    d = S / "libraries"
    return len(list(d.rglob("*.jar"))) if d.is_dir() else 0


for attempt in range(1, 4):
    print(f"\n===== 第 {attempt} 轮 (libraries={lib_count()}) =====")
    cmd = [JAVA, "-jar", str(S / "installer.jar"), "--installClient", str(S), "--mirror", MIRROR]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
    print(f"rc={r.returncode} 用时 {time.time()-t0:.1f}s libraries={lib_count()}")
    print("\n".join(lines[-6:]))
    if r.returncode == 0:
        break

print("\n=== 产物 ===")
d = S / "versions"
for p in sorted(d.iterdir()):
    print(" ", p.name, [f.name for f in p.iterdir()])
