"""小窗口回归：窗口压到最小尺寸时，三页都不能有控件被压扁（按钮露不全）。

用户反馈（m11028）「在往小调整窗口的时候自动调整分辨率使按键能够完整显示」。

判据沿用 `probe_squeeze.py` 的思路：`winfo_reqwidth() > winfo_width() + 2`
就是「这个控件想要更宽，但父容器只给了这么点」——文字截断、按钮半截都长这样。
注意**不能**用「超出父控件右边缘」判断：`ScrollFrame.inner` 里的滚动画布天生比
可视区高/宽，那不是 bug。

用法：
    python tools/smoke_small_window.py          # 三个页面依次跑（各自独立进程）
    python tools/smoke_small_window.py home     # 只跑一页

⚠ 每页必须独立进程：同进程建第二个 App() 时 `images._CACHE` 里缓存着上一个
root 的 PhotoImage，`page_home.py` 的 hero canvas 会抛
`_tkinter.TclError: can't invoke "image" command: application has been destroyed`。
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 最小窗口尺寸（和 App.minsize 一致）。窗口真正能缩到这里，所以必须在这
# 个尺寸下保证完整显示；再小就交给 minsize 拦住了。
MIN_W, MIN_H = 880, 560

# 允许的被压量：2px 是 Tk 的取整误差（边框/内边距），再多就是真截断。
TOLERANCE = 2

# 明确豁免的控件类：Canvas 自己被压扁不影响显示（内容按真实宽度重画），
# Label 有 wraplength 兜底也算合格 —— 只要换行后高度够。这两类都排除掉，
# 免得为了一个像素的 padding 把回归搞成红色。
SKIP_CLASSES = {"TScrollbar"}

FAIL: list[str] = []


def say(text: str = "") -> None:
    print(text, flush=True)


def check(cond: bool, msg: str) -> None:
    if cond:
        say(f"  ok   {msg}")
    else:
        FAIL.append(msg)
        say(f"  FAIL {msg}")


def squeeze(page, limit: int = 0) -> list[tuple[int, str, str, int, int]]:
    """返回 [(超出 px, 类名, 文字, got, req), ...]，按超出降序。"""
    out = []
    stack = [page]
    while stack:
        node = stack.pop()
        try:
            stack.extend(node.winfo_children())
            if not node.winfo_ismapped():
                continue
            req, got = node.winfo_reqwidth(), node.winfo_width()
            cls = node.winfo_class()
        except Exception:                              # noqa: BLE001
            continue
        if cls in SKIP_CLASSES:
            continue
        if req > 10 and got + TOLERANCE < req:
            txt = ""
            try:
                txt = str(node.cget("text"))[:24]
            except Exception:                          # noqa: BLE001
                pass
            out.append((req - got, cls, txt, got, req))
    out.sort(reverse=True)
    return out[:limit] if limit else out


def one(page: str) -> None:
    from mclite.ui import app as A

    say(f"=== {page}")
    a = A.App()
    a.update()
    a.create_pages()
    a.show_page(page)
    a.geometry(f"{MIN_W}x{MIN_H}")
    settle(a, 1.6)

    # minsize 生效后实际尺寸可能比请求大 2px（无边框窗口的缩放边框），按实际的来
    real_w, real_h = a.winfo_width(), a.winfo_height()
    say(f"  实际窗口 {real_w}x{real_h}，页面 {a._pages[page].winfo_width()}x"
        f"{a._pages[page].winfo_height()}")

    rows = squeeze(a._pages[page])
    for over, cls, txt, got, req in rows[:10]:
        say(f"  +{over:4d}px {cls:10s} got={got:4d} req={req:4d} {txt!r}")
    check(not rows, f"{page} 最小尺寸下没有控件被压扁（{len(rows)} 个）")

    # 再压到几档中间宽度，确认自适应不是只在最小尺寸生效
    for w, h in ((1000, 640), (1160, 724)):
        a.geometry(f"{w}x{h}")
        settle(a, 1.0)
        rows = squeeze(a._pages[page])
        check(not rows, f"{page} {w}x{h} 没有被压扁的控件（{len(rows)} 个）")

    a.destroy()


def settle(a, sec: float) -> None:
    end = time.time() + sec
    while time.time() < end:
        try:
            a.update()
        except Exception:                              # noqa: BLE001
            return
        time.sleep(0.02)


def main() -> None:
    if len(sys.argv) > 1:
        one(sys.argv[1])
        say()
        say("ALL PASS" if not FAIL else f"{len(FAIL)} 项不合格")
        sys.exit(0 if not FAIL else 1)
    # 父进程只负责串行拉起子进程并按退出码汇总（子进程各自有独立的 Tk）
    bad = 0
    for page in ("home", "install", "settings"):
        rc = subprocess.run([sys.executable, "-u", str(Path(__file__).resolve()),
                             page], check=False).returncode
        if rc != 0:
            bad += 1
        say()
    say("ALL PASS" if not bad else f"{bad} 个页面不合格")
    sys.exit(0 if not bad else 1)


if __name__ == "__main__":
    main()
