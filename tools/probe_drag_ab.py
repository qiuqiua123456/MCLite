"""A/B：每种状态起一个独立进程，避免同进程连续测量的漂移。

调用 probe_drag_one.py <mode> <page>，收集结果排成表。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable or r"G:\python\python.exe"
ONE = ROOT / "tools" / "probe_drag_one.py"

MODES = [
    ("baseline", "现状"),
    ("topbar_nodraw", "顶栏不重画"),
    ("topbar_solid_bg", "渐变换一条纯色"),
    ("topbar_tuple_fonts", "命名字体改元组"),
    ("topbar_no_text", "前景不写字"),
]


def run(mode: str, page: str) -> dict | None:
    try:
        cp = subprocess.run(
            [PY, "-u", str(ONE), mode, page],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=180, cwd=str(ROOT),
        )
    except subprocess.TimeoutExpired:
        return None
    for line in reversed(cp.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    print(f"  [{mode}] 无输出; stderr={cp.stderr.strip()[:200]}")
    return None


def main() -> int:
    page = sys.argv[1] if len(sys.argv) > 1 else "home"
    print(f"\n--- {page} 页，16ms 拖动 1120→1300，每档独立进程、3 轮取中位")
    print(f"{'状态':28s} {'中位':>8s} {'最差轮':>8s} {'掉帧':>6s}  三轮")
    for mode, label in MODES:
        r = run(mode, page)
        if not r:
            continue
        rounds = ", ".join(f"{v:.1f}" for v in r["rounds"])
        print(f"{label:28s} {r['mid']:8.1f} {r['worst_round']:8.1f} {r['over']:6.0f}  ({rounds})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
