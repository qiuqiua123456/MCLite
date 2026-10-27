"""打印实际会执行的命令行。用法：dump_cmd.py <版本> <游戏目录>"""
import sys
from pathlib import Path

sys.path.insert(0, ".")
from mclite import java as javamod
from mclite.launcher import GameLauncher, LaunchOptions

gid = sys.argv[1]
game = Path(sys.argv[2])
java = javamod.pick_for_version(javamod.detect_all(), 17)
launcher = GameLauncher(game)
cmd = launcher.build_command(gid, java, LaunchOptions(gid, player_name="Steve"))
for i, a in enumerate(cmd):
    if a == "-cp" or a == "-p":
        print(f"[{i}] {a}")
        nxt = cmd[i + 1]
        sep = ";" if ";" in nxt else (":" if ":" in nxt and len(nxt) > 3 else None)
        if sep:
            for part in nxt.split(sep):
                print("     ", part)
        else:
            print("     ", nxt)
    elif len(a) > 400:
        print(f"[{i}] <{len(a)} 字符> {a[:200]}…")
    else:
        print(f"[{i}] {a}")
