"""打印某个版本合并后的 jvm / game 参数与 classpath 条目。用法：dump_args.py <版本> <游戏目录>"""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
from mclite.launcher import GameLauncher

gid = sys.argv[1]
game = Path(sys.argv[2])
g = GameLauncher(game)
v = g.load_version(gid)
print("id:", v.get("id"), "mainClass:", v.get("mainClass"))
print("inheritsFrom:", v.get("inheritsFrom"), "_jar_from:", v.get("_jar_from"))
args = v.get("arguments") or {}
print("\n--- jvm ---")
for a in args.get("jvm") or []:
    print(" ", json.dumps(a, ensure_ascii=False)[:300])
print("\n--- game ---")
for a in args.get("game") or []:
    print(" ", json.dumps(a, ensure_ascii=False)[:300])
print("\n--- libraries (%d) ---" % len(v.get("libraries") or []))
