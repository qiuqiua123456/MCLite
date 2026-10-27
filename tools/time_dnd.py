import sys, time
sys.path.insert(0, r"F:\MCLite")
from mclite.ui.app import App
app = App(); app.create_pages()
for _ in range(3):
    app.update_idletasks(); app.update()
print("dnd_ok =", app._dnd_ok)
t = time.perf_counter()
n = app.add_drop_target(app._container)
print("add_drop_target(container) = %.1f ms" % ((time.perf_counter()-t)*1000))
def count(w):
    s = 1
    for c in w.winfo_children():
        s += count(c)
    return s
print("widgets under container:", count(app._container))
# 模拟切换后 60ms 的重新登记
for key in ("mods","home"):
    app.show_page(key); app.update()
    t = time.perf_counter(); app.add_drop_target(app._pages[key])
    print("re-register %s = %.1f ms" % (key, (time.perf_counter()-t)*1000))
app.destroy()
