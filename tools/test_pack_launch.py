"""启动刚装好的整合包实例，看能不能真的进主菜单。

用临时目录里的 Sodium Plus（Quilt 1.20.1），离线用户名，抓日志里的
「Sound engine started」「Created: ... minecraft:textures/atlas」之类
启动成功标志，超时就杀进程。
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

GAME = Path(r"C:\Users\qiu\AppData\Local\Temp\mclite_packtest_slxsdo0f\.minecraft")
VID = "Sodium Plus 2.2.11"
LIMIT = 300


def main() -> int:
    from mclite import java, launcher

    js = java.detect_all(GAME)
    ji = java.pick_for_version(js, 17)
    print("Java:", ji.path, ji.version)

    L = launcher.GameLauncher(GAME)
    opts = launcher.LaunchOptions(
        version_id=VID,
        player_name="Tester",
        memory_mb=2048,
    )
    # 先把完整命令行拼出来，便于排查
    cmd = L.build_command(VID, ji, opts)
    print("命令行长度:", len(cmd))
    print("mainClass 在命令行里:",
          any("KnotClient" in c for c in cmd))
    print("gameDir 在命令行里:", any("mclite_packtest" in c for c in cmd))

    t0 = time.time()
    proc = subprocess.Popen(
        cmd, cwd=str(GAME), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
    )
    marks = {
        "Setting user": False,
        "LWJGL": False,
        "Sound engine started": False,
        "Created:": False,
        "OpenAL": False,
        "Backend library": False,
        "Error": False,
        "Exception": False,
        "Mixin": False,
    }
    lines = 0
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            lines += 1
            s = line.rstrip()
            for k in marks:
                if k in s:
                    marks[k] = True
            if lines <= 60 or "ERROR" in s or "FATAL" in s or "Exception" in s:
                print(f"[{time.time() - t0:6.1f}s] {s[:200]}")
            if time.time() - t0 > LIMIT:
                print("=== 超时，结束进程 ===")
                break
            if proc.poll() is not None:
                break
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()

    print(f"=== 结束：{lines} 行日志，{time.time() - t0:.0f}s，返回码 {proc.returncode} ===")
    for k, v in marks.items():
        print(f"   {k:24s} {'✔' if v else '·'}")
    return 0 if not marks["FATAL"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
