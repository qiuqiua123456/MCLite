"""模拟「别人第一次运行」：干净的 APPDATA + 不存在的游戏目录，看会不会崩。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.test_exe import capture_window, find_window, kill_tree   # noqa: E402

EXE = Path(r"F:\MCLite\dist\MCLite.exe")
SHOTS = Path(r"F:\MCLite\shots")
ROOT = Path(os.environ.get("TEMP", ".")) / "mclite_firstrun"


def main() -> int:
    if ROOT.exists():
        shutil.rmtree(ROOT, ignore_errors=True)
    appdata = ROOT / "AppData"
    appdata.mkdir(parents=True)

    env = dict(os.environ)
    env["APPDATA"] = str(appdata)
    env.pop("MCLITE_NO_BROWSER", None)

    kill_tree("MCLite")
    proc = subprocess.Popen([str(EXE)], env=env)
    print("启动 pid:", proc.pid, "APPDATA ->", appdata)

    hwnd = None
    for _ in range(40):
        time.sleep(0.5)
        hwnd = find_window("MCLite")
        if hwnd:
            break
    print("窗口句柄:", hwnd)
    if not hwnd:
        print("FAIL: 没找到窗口")
        proc.kill()
        return 1

    time.sleep(3.0)
    img = capture_window(hwnd)
    SHOTS.mkdir(exist_ok=True)
    out = SHOTS / "firstrun.png"
    img.save(out)
    print("截图:", out, img.size)

    cfg_file = appdata / "MCLite" / "config.json"
    print("配置文件存在:", cfg_file.exists())
    if cfg_file.exists():
        data = json.loads(cfg_file.read_text("utf-8"))
        print("  game_dir:", data.get("game_dir"))
        print("  theme:", data.get("theme"), "username:", data.get("username"))
        print("  accounts:", len(data.get("accounts") or []))
    else:
        print("（启动器只在改设置时才写配置，没写也算正常）")

    print("进程还活着:", proc.poll() is None)
    kill_tree("MCLite")
    time.sleep(1.0)
    alive = subprocess.run(["tasklist", "/FI", "IMAGENAME eq MCLite.exe"],
                          capture_output=True, text=True).stdout
    print("残留:", "MCLite.exe" in alive)
    shutil.rmtree(ROOT, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
