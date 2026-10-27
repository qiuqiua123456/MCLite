"""在真实 GUI 里点一遍「安装加载器」：选 Fabric → 点开始安装 → 等到结束。

用法：python tools/gui_fabric_install.py [MC版本] [加载器]
"""
import sys
import time

sys.path.insert(0, ".")
import tkinter as tk

from mclite.ui.app import App
from mclite.ui.loader_dialog import LoaderDialog

mc = sys.argv[1] if len(sys.argv) > 1 else "1.20.1"
kind = sys.argv[2] if len(sys.argv) > 2 else "fabric"

app = App()
app.update()

result = {"done": False, "ok": False, "msg": "", "vid": ""}


def on_done(vid: str) -> None:
    result.update(done=True, ok=True, vid=vid)


def pump(seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.02)


dlg = LoaderDialog(app, mc, on_done=on_done)
dlg.grab_set()
dlg._set_tab(kind)

print(f"等待 {kind} 版本列表…")
deadline = time.time() + 30
while time.time() < deadline and not dlg._versions:
    pump(0.1)
if not dlg._versions:
    print("版本列表拉取失败")
    raise SystemExit(1)
print("版本数:", len(dlg._versions), "第一个:", dlg._versions[0].version)

dlg._select(dlg._versions[0])
pump(0.2)
print("点击开始安装…")
dlg._install()

start = time.time()
while time.time() - start < 420 and not result["done"] and dlg.winfo_exists():
    pump(0.2)
    if not dlg._installing and not result["done"] and dlg._log_text():
        pass
if not result["done"]:
    print("安装没有完成（超时或窗口被关）")
    raise SystemExit(1)
print("安装完成:", result["vid"], f"用时 {time.time() - start:.1f}s")
print("版本目录:", dlg.app.cfg.game_dir)
try:
    dlg.destroy()
except tk.TclError:
    pass
app.destroy()
