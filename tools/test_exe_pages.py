"""在打包后的 exe 里逐页截图，验证单文件版的各个页面都正常。

用 `MCLite.exe --page <name>` 直接打开目标页，避免注入鼠标事件。
``mods`` 现在落在开始页的「模组」页签上（--page mods 会切过去）。
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_exe import EXE, capture_window, find_window, kill_tree  # noqa: E402

PAGES = ["home", "mods", "install", "settings"]
WAIT = {"home": 6.0, "mods": 6.0, "install": 14.0, "settings": 6.0}


def main() -> int:
    outdir = Path(__file__).resolve().parent.parent / "shots"
    outdir.mkdir(parents=True, exist_ok=True)
    for name in PAGES:
        kill_tree(EXE.stem)
        time.sleep(0.5)
        subprocess.Popen([str(EXE), "--page", name], cwd=str(EXE.parent))
        hwnd = None
        for _ in range(60):
            time.sleep(0.5)
            hwnd = find_window()
            if hwnd:
                break
        if not hwnd:
            print("找不到窗口:", name)
            kill_tree(EXE.stem)
            return 2
        time.sleep(WAIT[name])
        img = capture_window(hwnd)
        path = outdir / f"exe_{name}.png"
        img.save(path)
        print("saved ->", path, img.size)
        kill_tree(EXE.stem)
        time.sleep(1.0)
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
