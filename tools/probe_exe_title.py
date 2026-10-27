"""启动 dist\\MCLite.exe，读出窗口标题（验证版本号已经打进 exe）。

跑法：G:\\python\\python.exe tools\\probe_exe_title.py [exe路径]
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from ctypes import wintypes

u = ctypes.windll.user32
u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u.GetWindowTextW.restype = ctypes.c_int
u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
u.IsWindowVisible.argtypes = [wintypes.HWND]
u.IsWindowVisible.restype = wintypes.BOOL

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def titles_of(pid: int) -> list[str]:
    found: list[str] = []

    def cb(hwnd, _lparam):
        owner = wintypes.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and u.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(256)
            u.GetWindowTextW(hwnd, buf, 256)
            if buf.value.strip():
                found.append(buf.value)
        return True

    u.EnumWindows(WNDENUMPROC(cb), 0)
    return found


def main() -> int:
    exe = sys.argv[1] if len(sys.argv) > 1 else r"F:\MCLite\dist\MCLite.exe"
    proc = subprocess.Popen([exe])
    try:
        seen: list[str] = []
        for _ in range(160):
            time.sleep(0.25)
            seen = titles_of(proc.pid)
            if seen:
                break
        print("窗口标题 =", repr(seen[0]) if seen else "(没抓到)", flush=True)
        return 0 if seen else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
