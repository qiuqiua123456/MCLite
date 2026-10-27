"""打包一份可以直接发给别人的发布包（zip：exe + 使用说明）。"""

from __future__ import annotations

import hashlib
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(r"F:\MCLite")
EXE = ROOT / "dist" / "MCLite.exe"
RELEASE = ROOT / "release"
# 版本号直接取源码里的 __version__，避免和 mclite/__init__.py 脱节
VERSION = re.search(
    r'__version__\s*=\s*"([^"]+)"',
    (ROOT / "mclite" / "__init__.py").read_text("utf-8"),
).group(1)
ZIP = ROOT / "dist" / f"MCLite-{VERSION}-win64.zip"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fp:
        for chunk in iter(lambda: fp.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def main() -> int:
    if not EXE.is_file():
        print("找不到 exe:", EXE)
        return 1
    payload = RELEASE / f"MCLite-{VERSION}"
    if payload.exists():
        shutil.rmtree(payload)
    payload.mkdir(parents=True)

    shutil.copy2(EXE, payload / "MCLite.exe")

    # 说明用 UTF-8 BOM 存，记事本打开不会乱码
    src_txt = RELEASE / "使用说明.txt"
    text = src_txt.read_text("utf-8")
    (payload / "使用说明.txt").write_text(text, encoding="utf-8-sig")

    ZIP.parent.mkdir(parents=True, exist_ok=True)
    ZIP.unlink(missing_ok=True)
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for item in sorted(payload.iterdir()):
            arc = f"MCLite-{VERSION}/{item.name}"
            zf.write(item, arc)
            print("  +", arc)

    print()
    print("exe :", EXE.stat().st_size, "B", sha256(EXE))
    print("zip :", ZIP.stat().st_size, "B", sha256(ZIP))
    print("目录:", payload)

    with zipfile.ZipFile(ZIP) as zf:
        for info in zf.infolist():
            print(f"  {info.filename}  {info.file_size} B -> {info.compress_size} B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
