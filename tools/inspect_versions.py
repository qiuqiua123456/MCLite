import sys
from pathlib import Path

sys.path.insert(0, ".")
from mclite.launcher import list_installed_versions, version_meta

gd = Path(sys.argv[1] if len(sys.argv) > 1 else r"G:\.minecraft")
print("游戏目录:", gd)
for v in list_installed_versions(gd):
    m = version_meta(gd, v)
    print("  {v}: type={t} java={j} jar={h} inherits={i} main={m}".format(
        v=v, t=m["type"], j=m["javaVersion"], h=m["has_jar"],
        i=m["inherits"] or "-", m=m["mainClass"]))
