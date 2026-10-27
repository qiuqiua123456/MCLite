"""按实例隔离的方式启动一个版本，验证 mod 真的被加载。

用法：python tools\\probe_instance_launch.py [版本号] [秒数]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mclite import instances  # noqa: E402
from mclite.java import detect_all, pick_for_version, required_java  # noqa: E402
from mclite.launcher import GameLauncher, LaunchOptions  # noqa: E402
from mclite.versionmeta import resolve_libraries  # noqa: E402

GAME = Path("G:/.minecraft")


def main() -> int:
    vid = sys.argv[1] if len(sys.argv) > 1 else "modpack"
    seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 35.0

    launcher = GameLauncher(GAME)
    vjson = launcher.load_version(vid)
    need = required_java(vjson)
    java = pick_for_version(detect_all(GAME, ""), need)
    if java is None:
        print(f"没有 Java {need}+")
        return 1

    sep = instances.effective(GAME, vid, False)
    inst = instances.game_dir_for(GAME, vid, sep)
    instances.ensure_instance(inst)
    mods = list((inst / "mods").glob("*.jar")) if (inst / "mods").is_dir() else []
    print(f"版本 {vid}  隔离={sep}  游戏目录={inst}  mods={len(mods)}  Java={java.version}")

    opts = LaunchOptions(
        version_id=vid,
        player_name="Steve",
        memory_mb=4096,
        width=900,
        height=560,
        instance_dir=inst if sep else None,
    )
    res = launcher.launch(vid, java, opts)
    print("pid", res.process.pid, "log", res.log_path)

    started = time.time()
    seen = 0
    while time.time() - started < seconds:
        time.sleep(1.0)
        if res.process.poll() is not None:
            break
        if res.log_path and res.log_path.is_file():
            lines = res.log_path.read_text("utf-8", "replace").splitlines()
            if len(lines) > seen:
                for line in lines[seen:]:
                    if any(k in line for k in ("Loading Minecraft", "mods", "Mixin", "GLFW", "Setting user",
                                               "Backend library", "OpenAL", "Sound engine")):
                        print("  |", line[:150])
                seen = len(lines)

    alive = res.process.poll() is None
    print("仍在运行" if alive else f"已退出 rc={res.process.returncode}")
    if alive:
        res.process.terminate()
    if res.log_path and res.log_path.is_file():
        text = res.log_path.read_text("utf-8", "replace")
        for key in ("Loading Minecraft", "Successfully loaded", "GLFW error", "Sound engine started"):
            hits = [ln for ln in text.splitlines() if key in ln]
            if hits:
                print(f"  [{key}] {hits[0][:160]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
