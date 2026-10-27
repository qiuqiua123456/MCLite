"""列出 install_profile 里缺失的库文件。用法：probe_missing_libs.py <installer.jar> <game_dir>"""
import json
import sys
import zipfile
from pathlib import Path

jar = Path(sys.argv[1])
game = Path(sys.argv[2])
with zipfile.ZipFile(jar) as z:
    prof = json.loads(z.read("install_profile.json").decode("utf-8"))

missing = []
present = 0
for lib in prof.get("libraries") or []:
    art = (lib.get("downloads") or {}).get("artifact") or {}
    path = art.get("path")
    if not path:
        continue
    dest = game / "libraries" / path
    if dest.is_file() and dest.stat().st_size > 0:
        present += 1
    else:
        missing.append((path, art.get("url", ""), lib.get("name", "")))

print(f"已存在 {present}，缺失 {len(missing)}")
for path, url, name in missing:
    print("  -", name)
    print("    ", url)
