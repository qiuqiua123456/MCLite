"""端到端验证：整合包在线下载 → 解包 → 装成独立版本。

在一个临时游戏目录里跑，不碰用户真实的 .minecraft。
流程与界面完全一致：搜索 → 选项目 → 选版本 → DownloadBrowser._fetch_pack
→ PackInstallDialog → packdetect.install_any。
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def pump(app, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        try:
            app.update_idletasks()
            app.update()
        except Exception:                            # noqa: BLE001
            return
        time.sleep(0.02)


def wait_for(app, cond, timeout: float, label: str) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        pump(app, 0.1)
    print(f"TIMEOUT  {label}（{timeout:.0f}s）")
    return False


def main() -> int:
    from mclite.ui.app import App

    game = Path(tempfile.mkdtemp(prefix="mclite_packtest_")) / ".minecraft"
    game.mkdir(parents=True, exist_ok=True)
    print(f"临时游戏目录：{game}")

    app = App()
    app.withdraw()
    app.cfg.set("game_dir", str(game))
    app.create_pages()
    app.update_idletasks()

    app.show_page("install")
    install = app._pages["install"]
    install._tabs.set("modpack", fire=True)
    pump(app, 0.3)

    browser = install._browser
    print(f"browser ptype = {browser._ptype}")
    if browser._ptype != "modpack":
        print("FAIL 页签没有切到整合包")
        app.destroy()
        return 1

    browser._entry_var.set("优化")
    browser.do_search()
    ok = wait_for(app, lambda: bool(browser._projects), 60, "搜索整合包")
    print(f"搜索结果：{len(browser._projects)} 个")
    if not ok:
        app.destroy()
        return 1

    # 选一个适配 1.20.1 + fabric 的整合包
    browser._ver_var.set("1.20.1")
    browser._loader = "fabric"
    browser._loader_btn.set_text("Fabric")
    browser.do_search()
    wait_for(app, lambda: bool(browser._projects), 60, "按 1.20.1/fabric 重搜")
    print(f"筛选后：{len(browser._projects)} 个")

    picked = None
    for p in browser._projects:
        browser._pick(p)
        wait_for(app, lambda: bool(browser._versions), 40, f"{p.title} 的版本")
        if browser._versions:
            picked = p
            break
    if picked is None:
        print("FAIL 没有任何可下载的版本")
        app.destroy()
        return 1
    print(f"选中的整合包：{picked.title}（{len(browser._versions)} 个版本）")

    browser._pick_version(browser._versions[0])
    v = browser._versions[0]
    f = __import__("mclite.modrinth", fromlist=["primary_file"]).primary_file(v)
    print(f"版本 {v.version_number} / {v.game_versions} / {v.loaders} → {f.filename} ({f.size_label})")

    browser.download_selected()
    ok = wait_for(app, lambda: browser._dl_btn._enabled and browser._status.cget("text").find("解包") >= 0,
                  300, "下载整合包")
    print(f"下载状态：{browser._status.cget('text')}")
    if not ok:
        app.destroy()
        return 1

    # 找安装窗口，等它跑完
    import tkinter as tk

    def find_dialog():
        for w in app.winfo_children():
            if isinstance(w, tk.Toplevel):
                return w
        return None

    dlg = find_dialog()
    if dlg is None:
        print("FAIL 没有出现安装窗口")
        app.destroy()
        return 1
    print("安装窗口已出现，等待解包安装…")
    ok = wait_for(app, lambda: getattr(dlg, "_finished", False), 900, "解包安装")
    status = dlg._status.cget("text") if hasattr(dlg, "_status") else ""
    print(f"安装结果：{status}")
    try:
        dlg.destroy()
    except Exception:                                # noqa: BLE001
        pass

    versions = list((game / "versions").iterdir()) if (game / "versions").exists() else []
    print(f"游戏目录里的版本：{[p.name for p in versions]}")

    good = ok and bool(versions)
    print("PASS 整合包在线下载 + 安装全链路" if good else "FAIL 链路未走通")
    app.destroy()
    return 0 if good else 1


if __name__ == "__main__":
    raise SystemExit(main())
