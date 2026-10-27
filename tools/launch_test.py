"""命令行启动测试：python tools/launch_test.py <版本号> [游戏目录] [秒数]"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mclite.java import detect_all, pick_for_version
from mclite.launcher import GameLauncher, LaunchOptions


def main() -> int:
    vid = sys.argv[1] if len(sys.argv) > 1 else "1.20.1"
    game_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(r"G:\.minecraft")
    seconds = float(sys.argv[3]) if len(sys.argv) > 3 else 30.0

    gl = GameLauncher(game_dir)
    javas = detect_all(game_dir)
    print("检测到 Java:", [(j.major, str(j.path)) for j in javas])

    from mclite.java import required_java
    vjson = gl.load_version(vid)
    need = required_java(vjson) or 17
    java = pick_for_version(javas, need)
    if java is None:
        print("没有可用的 Java")
        return 1
    print(f"版本 {vid} 需要 Java {need}+，选用 {java.label}")

    opts = LaunchOptions(version_id=vid, player_name="Steve", memory_mb=4096)
    res = gl.launch(vid, java, opts)
    if not res.ok:
        print("启动失败:", res.error)
        return 2
    print("PID", res.process.pid)

    print("日志:", res.log_path)
    lines: list[str] = []
    seen = 0

    deadline = time.time() + seconds
    while time.time() < deadline:
        if res.process.poll() is not None:
            break
        if res.log_path and res.log_path.is_file():
            try:
                text = res.log_path.read_text("utf-8", errors="replace")
            except OSError:
                text = ""
            new = text.splitlines()
            for line in new[seen:]:
                print("  [game]", line, flush=True)
            lines = new
            seen = len(new)
        time.sleep(0.8)

    alive = res.process.poll() is None
    print(f"--- {seconds:.0f}s 后进程{'仍在运行' if alive else '已退出'} "
          f"(code={res.process.poll()})")
    if alive:
        res.process.kill()
        time.sleep(1)
    crash = [ln for ln in lines if "Exception" in ln or "Error" in ln or "FAILED" in ln]
    if crash:
        print("--- 可疑日志行:")
        for ln in crash[:10]:
            print("   ", ln)
    return 0 if alive else 3


if __name__ == "__main__":
    raise SystemExit(main())
