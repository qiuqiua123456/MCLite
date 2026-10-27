"""把发布 zip 解到别处，当成「别人收到」跑一遍。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.test_exe import capture_window, find_window, kill_tree   # noqa: E402

ZIP = Path(r"F:\MCLite\dist\MCLite-1.6.1-win64.zip")
DEST = Path(os.environ.get("TEMP", ".")) / "mclite_recipient"
SHOT = Path(r"F:\MCLite\shots\recipient.png")


def main() -> int:
    if DEST.exists():
        shutil.rmtree(DEST, ignore_errors=True)
    DEST.mkdir(parents=True)
    with zipfile.ZipFile(ZIP) as zf:
        zf.extractall(DEST)
    exe = next(DEST.rglob("MCLite.exe"))
    txt = next(DEST.rglob("使用说明.txt"))
    print("解压到:", exe)
    print("说明文件:", txt, txt.stat().st_size, "B")
    print("说明前 60 字:", txt.read_text("utf-8-sig")[:60].replace("\n", " "))

    appdata = DEST / "appdata"
    appdata.mkdir()
    env = dict(os.environ)
    env["APPDATA"] = str(appdata)
    env.pop("MCLITE_NO_BROWSER", None)

    kill_tree("MCLite")
    proc = subprocess.Popen([str(exe)], env=env, cwd=str(exe.parent))
    hwnd = None
    for _ in range(40):
        time.sleep(0.5)
        hwnd = find_window("MCLite")
        if hwnd:
            break
    print("窗口:", hwnd, "进程存活:", proc.poll() is None)
    if not hwnd:
        print("FAIL 没窗口")
        kill_tree("MCLite")
        return 1
    time.sleep(3.0)
    capture_window(hwnd).save(SHOT)
    print("截图:", SHOT)
    kill_tree("MCLite")
    time.sleep(1.5)
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq MCLite.exe"],
                         capture_output=True, text=True).stdout
    print("残留:", "MCLite.exe" in out)
    shutil.rmtree(DEST, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
