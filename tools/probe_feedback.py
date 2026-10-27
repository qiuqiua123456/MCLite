"""测试一键反馈打包：打包后列出 zip 内容并打印大小。"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mclite import feedback  # noqa: E402
from mclite.config import Config  # noqa: E402
from mclite.java import detect_all  # noqa: E402


def main() -> int:
    cfg = Config()
    javas = detect_all()
    out = ROOT / "shots" / "tmp"
    path = feedback.collect(cfg, javas, dest_dir=out)
    print("zip:", path, path.stat().st_size, "B")
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            print(f"  {info.file_size:>9} {info.filename}")
        print("--- 系统信息.txt ---")
        print(zf.read("系统信息.txt").decode("utf-8"))
        print("--- 配置.json（令牌应已抹掉）---")
        cfg_text = zf.read("配置.json").decode("utf-8")
        print(cfg_text[:400])
        assert "refresh_token" not in cfg_text, "配置里还留着令牌！"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
