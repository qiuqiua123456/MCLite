"""矩阵定位：重建 16 行的开销到底来自可见性、ScrollFrame 的 canvas，还是 Tk 本身。

四种组合各测 destroy / create / update_idletasks 三段：
  A. 页面可见 + 行挂在 ScrollFrame.inner（现状）
  B. 页面可见 + 行挂在普通 Frame
  C. 窗口 withdraw + 行挂在 ScrollFrame.inner
  D. 窗口 withdraw + 行挂在普通 Frame
"""
from __future__ import annotations

import sys
import time
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mclite.ui import theme  # noqa: E402


def pump(app, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.update_idletasks()
        app.update()
        time.sleep(0.01)


def build_rows(parent, n=16) -> None:
    for i in range(n):
        head = tk.Frame(parent, bg=theme.BG_ALT)
        head.pack(fill="x")
        tk.Label(head, text=f"1.{i}", bg=theme.BG_ALT).pack(side="left")
        tk.Label(head, text="  1 个", bg=theme.BG_ALT).pack(side="left")
        row = tk.Frame(parent, bg=theme.BG_ALT)
        row.pack(fill="x")
        box = tk.Frame(row, bg=theme.BG_ALT)
        box.pack(side="left", fill="both", expand=True)
        tk.Label(box, text=f"1.{i}.1", bg=theme.BG_ALT).pack(fill="x")
        tk.Label(box, text="正式版  2024-01-01", bg=theme.BG_ALT).pack(fill="x")


def measure(target, tag: str) -> None:
    for round_ in range(3):
        t0 = time.perf_counter()
        for w in target.winfo_children():
            w.destroy()
        t1 = time.perf_counter()
        build_rows(target)
        t2 = time.perf_counter()
        target.update_idletasks()
        t3 = time.perf_counter()
        print(f"  {tag} #{round_}  destroy {1000*(t1-t0):7.1f} | create {1000*(t2-t1):6.1f} "
              f"| idle {1000*(t3-t2):7.1f} ms")


def main() -> int:
    root = tk.Tk()
    root.geometry("1160x724")
    theme.apply_style(root)

    body = tk.Frame(root, bg=theme.BG)
    body.pack(fill="both", expand=True)

    # 左：ScrollFrame；右：普通 Frame（两者尺寸一致，避免混淆）
    sf = theme.ScrollFrame(body, theme.BG_ALT)
    sf.pack(side="left", fill="both", expand=True)
    plain = tk.Frame(body, bg=theme.BG_ALT)
    plain.pack(side="left", fill="both", expand=True)

    pump(root, 0.6)
    print("scroll canvas", sf._canvas.winfo_width(), "x", sf._canvas.winfo_height(),
          "| plain", plain.winfo_width(), "x", plain.winfo_height())

    print("\nA 可见 + ScrollFrame.inner")
    measure(sf.inner, "A")
    print("\nB 可见 + 普通 Frame")
    measure(plain, "B")

    root.withdraw()
    pump(root, 0.3)
    print("\nC withdraw + ScrollFrame.inner")
    measure(sf.inner, "C")
    print("\nD withdraw + 普通 Frame")
    measure(plain, "D")

    root.deiconify()
    pump(root, 0.4)

    # E：Tk 完全独立的最小对照（无 ScrollFrame、无主题画布）
    print("\nE 独立 Toplevel + 普通 Frame（最小对照）")
    win = tk.Toplevel(root)
    win.geometry("400x600")
    box2 = tk.Frame(win)
    box2.pack(fill="both", expand=True)
    pump(root, 0.4)
    measure(box2, "E")

    root.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
