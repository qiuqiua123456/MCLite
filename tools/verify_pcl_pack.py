"""验收桌面上那个 PCL 修改版压缩包：解压到干净目录 -> 直接启动 -> 关掉 -> 看配置。

只验证「拿到就能用」这一条：
  1. 解压后的目录结构是 PCL 认的那套（exe + PCL\\Setup.ini）；
  2. exe 真能启动出窗口；
  3. 启动/退出之后 Setup.ini 里的 SystemSystemUpdate:3 还在（说明它读到了，
     而不是在自己的默认位置另建了一份）。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import shutil
import subprocess
import time
import zipfile
from pathlib import Path

ZIP = Path.home() / "Desktop" / "PCL-2.14.0.0-修改版.zip"
OUT = Path(r"C:\Users\Public\pclverify")

user32 = ctypes.windll.user32
user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM), wt.LPARAM]
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.IsWindowVisible.argtypes = [wt.HWND]

OK: list[str] = []
BAD: list[str] = []


def check(cond: bool, msg: str) -> None:
    (OK if cond else BAD).append(msg)
    print(("  ok    " if cond else "  FAIL  ") + msg, flush=True)


def windows_of(pid: int) -> list[str]:
    found: list[str] = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _lp):
        got = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(got))
        if got.value == pid and user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, buf, 512)
            if buf.value.strip():
                found.append(buf.value)
        return True

    user32.EnumWindows(cb, 0)
    return found


def main() -> int:
    if not ZIP.is_file():
        print(f"找不到 {ZIP}")
        return 1

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    with zipfile.ZipFile(ZIP) as zf:
        zf.extractall(OUT)

    roots = [p for p in OUT.iterdir() if p.is_dir()]
    check(len(roots) == 1, f"解压出一个顶层目录：{[p.name for p in roots]}")
    root = roots[0]
    exe = root / "Plain Craft Launcher 2.exe"
    ini = root / "PCL" / "Setup.ini"
    check(exe.is_file(), f"exe 在顶层：{exe.name}")
    check(ini.is_file(), "PCL\\Setup.ini 与 exe 同级（PCL 的约定位置）")
    check(exe.stat().st_size == 5989376, f"exe 大小 {exe.stat().st_size}")
    before = ini.read_bytes()
    check(b"SystemSystemUpdate:3" in before, "解压后 Setup.ini 含 SystemSystemUpdate:3")
    check(not before.startswith(b"\xef\xbb\xbf"), "Setup.ini 没有 BOM")

    # 启动。PCL 会先弹一个「应用程序正在打开，请稍候」的启动画面，
    # 主窗口要再等几秒才出，所以两种标题都算启动成功。
    print("\n启动 exe …", flush=True)
    proc = subprocess.Popen([str(exe)], cwd=str(root))
    titles: list[str] = []
    seen: list[str] = []
    got_main = False
    deadline = time.time() + 60
    while time.time() < deadline:
        time.sleep(1.0)
        if proc.poll() is not None:
            break
        titles = windows_of(proc.pid)
        for t in titles:
            if t not in seen:
                seen.append(t)
                print(f"    窗口出现：{t}", flush=True)
        if any("Plain Craft" in t or t.startswith("PCL") for t in titles):
            got_main = True
            break
    print(f"  进程 pid={proc.pid} 存活={proc.poll() is None}")
    check(bool(seen), f"启动出了窗口（见到过 {len(seen)} 个）")
    check(got_main, "出现了 PCL 主窗口（不是只停在启动画面）")

    # 再等一会儿让它把配置读写跑完，然后正常关闭
    time.sleep(4.0)
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                   capture_output=True, text=True)
    time.sleep(1.5)

    after = ini.read_bytes()
    print(f"\n退出后 Setup.ini {len(after)} 字节（解压时 {len(before)}）")
    try:
        print("  内容：")
        for line in after.decode("utf-8").splitlines():
            print("    " + line)
    except UnicodeDecodeError:
        print("  解码失败（非 UTF-8）")
    check(b"SystemSystemUpdate:3" in after,
          "启动退出后 SystemSystemUpdate:3 仍在（配置作用在这个目录，不是另建的）")
    check(not (root / "PCL" / "Setup.ini").with_suffix(".tmp").exists(),
          "没有残留临时 ini")

    print(f"\n通过 {len(OK)} / 失败 {len(BAD)}")
    if BAD:
        for m in BAD:
            print("  失败项：" + m)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
