"""看 cfwidget 返回结构，确认能不能按 fileID 找到下载直链。"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
CURL = r"C:\Windows\System32\curl.exe"


def fetch(url: str, timeout: int = 30) -> str:
    tmp = Path(tempfile.mkdtemp()) / "out.json"
    cmd = [CURL, "-sSL", "--max-time", str(timeout), "-A", UA, "-o", str(tmp), url]
    rc = subprocess.run(cmd, capture_output=True).returncode
    if rc != 0 or not tmp.exists():
        raise RuntimeError(f"curl rc={rc}")
    data = tmp.read_text("utf-8", "replace")
    tmp.unlink(missing_ok=True)
    return data


def main() -> None:
    url = "https://api.cfwidget.com/minecraft/mc-mods/fabric-api?version=1.20.1"
    data = json.loads(fetch(url))
    print("keys:", list(data))
    print("download:", json.dumps(data.get("download"), ensure_ascii=False))
    files = data.get("files") or []
    print("files:", len(files))
    for f in files[:3]:
        print("  ", json.dumps({k: f.get(k) for k in ("id", "name", "version", "type", "url")}, ensure_ascii=False))
    ids = {f.get("id") for f in files}
    print("has 4563440:", 4563440 in ids)


if __name__ == "__main__":
    main()
