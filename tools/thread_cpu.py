"""按线程粒度为某个 PID 采样 CPU，定位到底是谁在烧 CPU。"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import sys
import time

k32 = ctypes.windll.kernel32

TH32CS_SNAPTHREAD = 0x00000004
THREAD_QUERY_INFORMATION = 0x0040
PROCESS_QUERY_INFORMATION = 0x0400


class THREADENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD), ("cntUsage", wt.DWORD),
        ("th32ThreadID", wt.DWORD), ("th32OwnerProcessID", wt.DWORD),
        ("tpBasePri", wt.LONG), ("tpDeltaPri", wt.LONG), ("dwFlags", wt.DWORD),
    ]


class FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wt.DWORD), ("dwHighDateTime", wt.DWORD)]


def ft_to_sec(ft: FILETIME) -> float:
    return (ft.dwHighDateTime << 32 | ft.dwLowDateTime) / 1e7


def thread_times(tid: int) -> tuple[float, float] | None:
    h = k32.OpenThread(THREAD_QUERY_INFORMATION, False, tid)
    if not h:
        return None
    try:
        c, e, kern, user = FILETIME(), FILETIME(), FILETIME(), FILETIME()
        if not k32.GetThreadTimes(h, ctypes.byref(c), ctypes.byref(e),
                                  ctypes.byref(kern), ctypes.byref(user)):
            return None
        return ft_to_sec(kern), ft_to_sec(user)
    finally:
        k32.CloseHandle(h)


def list_threads(pid: int) -> list[int]:
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    if snap == -1:
        return []
    try:
        te = THREADENTRY32()
        te.dwSize = ctypes.sizeof(THREADENTRY32)
        tids: list[int] = []
        ok = k32.Thread32First(snap, ctypes.byref(te))
        while ok:
            if te.th32OwnerProcessID == pid:
                tids.append(te.th32ThreadID)
            ok = k32.Thread32Next(snap, ctypes.byref(te))
        return tids
    finally:
        k32.CloseHandle(snap)


def main() -> int:
    pid = int(sys.argv[1])
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else 4.0
    tids = list_threads(pid)
    if not tids:
        print("找不到线程（可能权限不足或 PID 不存在）")
        return 1

    base = {t: thread_times(t) for t in tids}
    time.sleep(secs)
    rows = []
    for t in tids:
        now = thread_times(t)
        b = base.get(t)
        if not now or not b:
            continue
        d = (now[0] - b[0]) + (now[1] - b[1])
        rows.append((round(d / secs * 100, 1), t))

    rows.sort(reverse=True)
    total = sum(r[0] for r in rows)
    print(f"PID {pid}  线程 {len(rows)}  采样 {secs}s  合计 {total:.0f}% of 1 核")
    print(f"{'核心占用%':>10}  {'线程 ID':>8}")
    for pct, tid in rows[:15]:
        print(f"{pct:>10.1f}  {tid:>8}")
    rest = sum(r[0] for r in rows[15:])
    if rest > 0.05:
        print(f"{rest:>10.1f}  （其余 {len(rows) - 15} 个线程合计）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
