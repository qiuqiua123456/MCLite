"""把登录弹窗强行切到「等待授权」状态并截图，用来检查设备码区域布局。"""
import sys
import time

sys.path.insert(0, ".")
import tkinter as tk

from mclite import auth
from mclite.ui.app import App
from mclite.ui.ms_login import MsLoginDialog


def pump(app, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.02)


app = App()
app.update()
dlg = MsLoginDialog(app)
dlg._cancel.set()
dlg._show_waiting()
fake = auth.DeviceLogin(user_code="K7QM2XW9",
                        verification_uri="https://www.microsoft.com/link",
                        device_code="x", interval=5, expires_in=900, message="")
dlg._on_code(fake)
pump(app, 0.6)
out = "shots/login_code.png"
dlg.update()
from PIL import ImageGrab
x, y = dlg.winfo_rootx(), dlg.winfo_rooty()
w, h = dlg.winfo_width(), dlg.winfo_height()
ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).save(out)
print("saved ->", out, (w, h))
try:
    dlg.destroy()
    app.destroy()
except tk.TclError:
    pass
