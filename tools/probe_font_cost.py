"""为什么 48 个控件的 create/idle/destroy 要 100-500ms？怀疑是字体解析。

对比四种字体写法，各建 16 行（=48 控件）并计时 create / idle / destroy。
"""
from __future__ import annotations

import sys
import time
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def pump(root, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        root.update_idletasks()
        root.update()
        time.sleep(0.01)


def build(parent, font_spec, n=16) -> None:
    for i in range(n):
        row = tk.Frame(parent)
        row.pack(fill="x")
        box = tk.Frame(row)
        box.pack(side="left", fill="both", expand=True)
        if font_spec is None:
            tk.Label(box, text=f"1.{i}.1").pack(fill="x")
            tk.Label(box, text="正式版 2024-01-01").pack(fill="x")
        else:
            tk.Label(box, text=f"1.{i}.1", font=font_spec).pack(fill="x")
            tk.Label(box, text="正式版 2024-01-01", font=font_spec).pack(fill="x")


def measure(parent, font_spec, tag: str) -> None:
    rows = []
    # 预热一轮（字体首次加载不计入）
    build(parent, font_spec)
    parent.update_idletasks()
    parent.update()
    for w in parent.winfo_children():
        w.destroy()
    parent.update_idletasks()

    for k in range(3):
        t0 = time.perf_counter()
        build(parent, font_spec)
        t1 = time.perf_counter()
        parent.update_idletasks()
        t2 = time.perf_counter()
        parent.update()
        t3 = time.perf_counter()
        for w in parent.winfo_children():
            w.destroy()
        t4 = time.perf_counter()
        rows.append((t1 - t0, t2 - t1, t3 - t2, t4 - t3))
        parent.update_idletasks()
        parent.update()
    print(f"  {tag:28s} create {1000*rows[-1][0]:6.1f} | idle {1000*rows[-1][1]:7.1f} "
          f"| draw {1000*rows[-1][2]:7.1f} | destroy {1000*rows[-1][3]:7.1f} ms")


def main() -> int:
    root = tk.Tk()
    root.geometry("900x700")
    pump(root, 0.5)

    body = tk.Frame(root)
    body.pack(fill="both", expand=True)
    pump(root, 0.3)

    print("每种 16 行 = 48 控件，取第 3 轮（已预热）：")
    measure(body, None, "默认字体")
    measure(body, "TkDefaultFont", "命名字体 TkDefaultFont")
    measure(body, ("Microsoft YaHei UI", 9), "元组字体 YaHei 9")
    measure(body, tkfont.Font(root, family="Microsoft YaHei UI", size=9),
            "Font 对象 YaHei 9")

    print("\n行数加倍（32 行 = 96 控件）：")
    measure(body, None, "默认字体 32行", )
    measure(body, ("Microsoft YaHei UI", 9), "元组 YaHei 32行")

    root.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
