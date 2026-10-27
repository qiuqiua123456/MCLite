"""验证 list_installed_versions 会把半装残留挡在列表外（用户反馈「哪来的」）。"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mclite.launcher import list_installed_versions, version_complete  # noqa: E402


def main() -> int:
    tmp = Path(tempfile.mkdtemp()) / ".minecraft"
    v = tmp / "versions"

    # 1) JSON 写了一半（安装中途被杀）
    (v / "broken").mkdir(parents=True)
    (v / "broken" / "broken.json").write_text('{"id": "brok', encoding="utf-8")

    # 2) jar 是 0 字节空壳
    (v / "emptyjar").mkdir(parents=True)
    (v / "emptyjar" / "emptyjar.json").write_text('{"id": "emptyjar"}', encoding="utf-8")
    (v / "emptyjar" / "emptyjar.jar").write_bytes(b"")

    # 3) 加载器 profile，父版本不在
    (v / "orphan-loader").mkdir(parents=True)
    (v / "orphan-loader" / "orphan-loader.json").write_text(
        '{"id": "orphan-loader", "inheritsFrom": "1.99"}', encoding="utf-8")

    # 4) 正常原版
    (v / "1.21").mkdir(parents=True)
    (v / "1.21" / "1.21.json").write_text('{"id": "1.21"}', encoding="utf-8")
    (v / "1.21" / "1.21.jar").write_bytes(b"x" * 100)

    # 5) 正常加载器（jar 在父版本里）
    (v / "fabric-loader-0.16-1.21").mkdir(parents=True)
    (v / "fabric-loader-0.16-1.21" / "fabric-loader-0.16-1.21.json").write_text(
        '{"id": "fabric-loader-0.16-1.21", "inheritsFrom": "1.21"}', encoding="utf-8")

    # 6) 完整目录里残留 .part（下载器半截文件，不该影响判定）
    (v / ".partdir").mkdir()
    (v / "1.21" / "1.21.jar.part").write_bytes(b"partial")

    expect_false = ["broken", "emptyjar", "orphan-loader", ".partdir"]
    expect_true = ["1.21", "fabric-loader-0.16-1.21"]
    ok = True
    for name in expect_false:
        got = version_complete(tmp, name)
        print(f"{'FAIL' if got else ' ok '}  {name} 版本完整={got} 期望 False")
        ok = ok and not got
    for name in expect_true:
        got = version_complete(tmp, name)
        print(f"{' ok ' if got else 'FAIL'}  {name} 版本完整={got} 期望 True")
        ok = ok and got

    listed = list_installed_versions(tmp)
    print("列表 ->", listed)
    if sorted(listed) != sorted(expect_true):
        print("FAIL 列表内容不对")
        ok = False
    order_ok = list_installed_versions(tmp) == expect_true or set(listed) == set(expect_true)
    print("PASS" if ok and order_ok else "FAILED")
    return 0 if ok and order_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
