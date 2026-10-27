"""复现用户反馈的 bug：切换配色后设置页卡死，只有切回其它页再回来才恢复。

用户原话（m08790）：「修复切换配色后设置界面卡死只有重新切换回设置才恢复的bug」。

做法：停在设置页 → 点一个主题按钮 → 等重建完成 → 检查
1. 当前页还是不是 settings；
2. settings 页的控件是否还是活着的（winfo 能查）；
3. settings 页的控件树是否被别的页面盖住（lift 顺序）；
4. 模拟点一下设置页上的按钮，看回调还灵不灵。
"""
from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FAIL: list[str] = []


def check(cond, msg):
    if not cond:
        FAIL.append(msg)
    print(("  ok   " if cond else "  FAIL ") + msg)


def settle(app, sec=1.0):
    end = time.time() + sec
    while time.time() < end:
        app.update()
        time.sleep(0.02)


def main() -> int:
    from mclite.ui import theme
    from mclite.ui.app import App

    app = App()
    app.create_pages()
    app.show_page("settings")
    settle(app, 1.5)

    print("=== 初始状态")
    print("  当前页:", app._current)
    print("  页面表:", sorted(app._pages))
    ps = app._pages["settings"]
    print("  settings widget:", ps)
    print("  settings 存在:", bool(ps.winfo_exists()))
    print("  settings 已 place:", ps.winfo_manager(), ps.place_info() or "无")
    print("  主题按钮数:", len(ps._theme_btns))

    # ---- 点主题按钮（走真实的 _set_theme 路径）
    print("\n=== 点击主题按钮 dark")
    try:
        ps._theme_btns["dark"]._on_release()
    except Exception:                              # noqa: BLE001
        print("  点按钮抛异常:")
        traceback.print_exc()
    settle(app, 2.0)

    print("\n=== 重建后")
    print("  当前页:", app._current)
    ps2 = app._pages.get("settings")
    print("  settings widget:", ps2)
    alive = False
    try:
        alive = bool(ps2.winfo_exists())
    except Exception:                              # noqa: BLE001
        print("  winfo_exists 抛异常:")
        traceback.print_exc()
    print("  settings 存在:", alive)
    print("  settings 已 place:", ps2.winfo_manager(), ps2.place_info() or "无")
    print("  主题按钮数:", len(getattr(ps2, "_theme_btns", {})))
    check(alive, "换主题后设置页控件还活着")
    check(app._current == "settings", f"换主题后仍停在设置页（_current={app._current}）")
    check(bool(ps2.winfo_manager()), "设置页仍然被 place 管理（不是被 place_forget）")

    # ---- 检查是不是被别的页面盖住（lift 顺序）
    order = []
    for key, page in app._pages.items():
        try:
            order.append((page.winfo_manager() != "", key,
                          page.tk.call("wm", "stackorder", ".") if False else 0))
        except Exception:                          # noqa: BLE001
            pass
    print("\n  place 中的页面:", [(k, p.winfo_manager()) for k, p in app._pages.items()])
    overlapping = [k for k, p in app._pages.items() if p.winfo_manager() and k != "settings"]
    check(not overlapping, f"没有其它页面同时 place 在设置页上面（实际 {overlapping}）")

    # ---- 设置页上的按钮还能不能点
    print("\n=== 点设置页的「保存设置」按钮")
    ok_click = {"done": False}
    orig = ps2.save_all

    def spy():
        ok_click["done"] = True

    ps2.save_all = spy
    try:
        ps2._save_btn._on_release()
    except Exception:                              # noqa: BLE001
        print("  抛异常:")
        traceback.print_exc()
    settle(app, 0.6)
    ps2.save_all = orig
    check(ok_click["done"], "换主题后设置页按钮回调仍能触发")

    # ---- 再切回设置页是否「恢复」（用户的绕过办法）
    app.show_page("home")
    settle(app, 0.6)
    app.show_page("settings")
    settle(app, 0.6)
    print("\n  切走再切回后 _current:", app._current)

    app.destroy()
    print()
    print(f"FAIL {len(FAIL)} 项")
    for f in FAIL:
        print("  - " + f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
