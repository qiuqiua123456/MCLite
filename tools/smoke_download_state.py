"""回归：切页签后不能残留上一个页签的标题 / 结果 / 版本列表。

跑法：python tools/smoke_download_state.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("PASS  " if cond else "FAIL  ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        FAILS.append(name)


def pump(app, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.update_idletasks()
        app.update()
        time.sleep(0.02)


def pump_until(app, cond, seconds: float = 25.0, step: float = 0.05) -> bool:
    """泵主循环直到 cond() 为真。Modrinth 有时要十几秒才回，固定 pump 容易假失败。"""
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.update_idletasks()
        app.update()
        if cond():
            # 再多泵几帧，让 after() 排队的渲染真正跑完
            for _ in range(6):
                app.update_idletasks()
                app.update()
                time.sleep(step)
            return True
        time.sleep(step)
    return False


def main() -> int:
    from mclite.ui.app import App

    app = App()
    app.create_pages()
    pump(app, 0.5)
    app.show_page("install")
    pump(app, 1.0)

    page = app._pages["install"]

    # 1) 模组页签搜一把，制造「残留」的前提
    page.open_browser("mod")
    pump(app, 0.8)
    br = page._browser
    check("打开模组页签后有浏览器实例", br is not None)
    if br is None:
        app.destroy()
        return 1
    br._entry_var.set("小地图")
    br.do_search()
    pump_until(app, lambda: len(br._projects) > 0)
    lhead_mod = br._lhead.cget("text")
    check("模组搜索有结果", len(br._projects) > 0, lhead_mod)

    # 2) 切到整合包：标题、左栏、右栏都必须换掉
    page.open_browser("modpack")
    pump(app, 1.2)
    lhead_pack = br._lhead.cget("text")
    check("切页签后标题不含旧关键词", "小地图" not in lhead_pack and "minimap" not in lhead_pack,
          lhead_pack)
    check("切页签后右栏清空", len(br._versions) == 0 and not br._vrows)
    check("切页签后下载按钮禁用", br._dl_btn._enabled is False)
    check("整合包页签显示加载器按钮", br._loader_visible is True)

    # ⚠ 左栏不再断言「清空」：从 1.7.x 起切页签会自动拉「热门内容」（用户反馈
    # 「不搜索就不显示结果」），所以左栏很快又有东西。真正要防的回归是「残留
    # 上一个页签的结果」—— 上一个页签是模组搜索「小地图」，整合包页签里绝不该
    # 出现那个项目。
    pump_until(app, lambda: not br._busy, seconds=25.0)
    titles = " ".join(p.title.lower() for p in br._projects)
    check("切页签后不残留模组的搜索结果", "minimap" not in titles and "小地图" not in titles,
          f"{len(br._projects)} 个整合包")

    # 3) 整合包搜索必须带加载器过滤（选 Forge 时结果里应有 forge）
    br._loader = "forge"
    br._sync_loader_btn()
    br._entry_var.set("优化")
    br.do_search()
    pump_until(app, lambda: len(br._projects) > 0)
    check("整合包搜索有结果", len(br._projects) > 0, br._lhead.cget("text"))
    p0 = br._projects[0] if br._projects else None
    if p0 is not None:
        print(f"      首个结果：{p0.title}  loaders={getattr(p0, 'loaders', None)}")

    # 4) 点项目 → 版本列表；再点另一个项目，旧版本请求的结果不能盖回来
    #    先把加载器过滤放开：上面为了验证「带过滤器搜索」硬设了 forge，而
    #    Fabulously Optimized 是 fabric 包，带着 forge 过滤去拉版本当然是 0 个。
    br._loader = ""
    br._sync_loader_btn()
    if len(br._projects) >= 1:
        br._pick(br._projects[0])
        pump_until(app, lambda: len(br._versions) > 0)
        n_first = len(br._versions)
        check("选中项目后拿到版本", n_first > 0, f"{n_first} 个")
        if len(br._projects) >= 2:
            br._pick(br._projects[1])
            pump(app, 5.0)
            rhead = br._rhead.cget("text")
            check("换项目后右栏标题跟着换",
                  br._projects[1].title[:6] in rhead or "版本" in rhead, rhead)

    # 5) 占位标签必须是 Entry 的子控件（否则溢出压住版本框）
    check("占位标签挂在输入框内", br._ph.winfo_parent() == str(br._entry),
          br._ph.winfo_parent())
    br._entry_var.set("")
    br._placeholder_visible()
    pump(app, 0.3)
    ph_w = br._ph.winfo_width()
    en_w = br._entry.winfo_width()
    check("占位标签不超出输入框宽度", ph_w <= en_w, f"ph={ph_w} entry={en_w}")

    app.destroy()
    print()
    if FAILS:
        print(f"{len(FAILS)} 项失败：" + ", ".join(FAILS))
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
