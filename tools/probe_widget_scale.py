"""最小对照：48 个 Label 的布局为什么要 200ms？按控件数扫一遍找常数。"""
from __future__ import annotations

import os
import sys
import time
import tkinter as tk
import tkinter.font as tkfont


def pump(root, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        root.update_idletasks()
        root.update()
        time.sleep(0.01)


def one_round(parent, n):
    t0 = time.perf_counter()
    for i in range(n):
        tk.Label(parent, text=f"行 {i}").pack(fill="x")
    t1 = time.perf_counter()
    parent.update_idletasks()
    t2 = time.perf_counter()
    for w in parent.winfo_children():
        w.destroy()
    t3 = time.perf_counter()
    parent.update_idletasks()
    return 1000 * (t1 - t0), 1000 * (t2 - t1), 1000 * (t3 - t2)


def main() -> int:
    print("PYTHON:", sys.version.split()[0], "| pid", os.getpid())
    root = tk.Tk()
    root.geometry("900x700")
    pump(root, 0.5)

    # 报告 DPI 与字体度量情况
    print("tk scaling:", root.tk.call("tk", "scaling"))
    try:
        print("系统 DPI:", root.winfo_fpixels("1i"))
    except Exception as exc:                       # noqa: BLE001
        print("DPI 查询失败:", exc)
    for name in ("TkDefaultFont", "TkTextFont", "TkFixedFont"):
        f = tkfont.nametofont(name)
        print(f"  {name}: family={f.actual('family')} size={f.actual('size')} "
              f"linespace={f.metrics('linespace')}")

    body = tk.Frame(root)
    body.pack(fill="both", expand=True)
    pump(root, 0.3)

    print("\n控件数 → (create, idle布局, destroy) ms，每档跑 3 次取最后：")
    for n in (1, 4, 8, 16, 32, 64, 128):
        best = None
        for _ in range(3):
            best = one_round(body, n)
            pump(root, 0.05)
        print(f"  {n:4d} 个 Label   create {best[0]:7.1f} | idle {best[1]:8.1f} "
              f"| destroy {best[2]:7.1f}")

    # 同样的东西放进一个不带任何样式的独立 Toplevel 对照
    print("\n独立 Toplevel 对照（64 个）：")
    win = tk.Toplevel(root)
    win.geometry("400x600")
    pump(root, 0.3)
    inner = tk.Frame(win)
    inner.pack(fill="both", expand=True)
    print("   ", one_round(inner, 64))

    root.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
