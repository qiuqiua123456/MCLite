"""真下一份 Java 运行时，验证自动下载链路。

用法：python tools\\probe_java_install.py [大版本号] [目标目录]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mclite import javaauto  # noqa: E402
from mclite.downloader import Progress  # noqa: E402


def main() -> int:
    major = int(sys.argv[1]) if len(sys.argv) > 1 else 17
    target = Path(sys.argv[2]) if len(sys.argv) > 2 else \
        Path(__import__("tempfile").gettempdir()) / "mclite_javatest"

    last = [0.0]

    def on_progress(p: Progress) -> None:
        now = time.time()
        if now - last[0] < 1.0:
            return
        last[0] = now
        print(f"  {p.done}/{p.total} 文件  {p.bytes_done / 1048576:.1f} MB  "
              f"{p.speed / 1048576:.2f} MB/s", flush=True)

    started = time.time()
    try:
        info = javaauto.install_java(target, major,
                                     on_log=lambda m: print("   ", m, flush=True),
                                     progress_cb=on_progress)
    except Exception as exc:                         # noqa: BLE001
        print(f"失败：{type(exc).__name__}: {exc}")
        return 1
    print(f"完成：Java {info.version} ({info.major}, {info.bits} 位) -> {info.path}")
    print(f"用时 {time.time() - started:.1f}s")
    print(f"installed_runtimes: {javaauto.installed_runtimes(target)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
