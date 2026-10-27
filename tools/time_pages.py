import sys, time
sys.path.insert(0, r"F:\MCLite")
from mclite.ui.app import App
app = App(); app.create_pages()
for _ in range(3):
    app.update_idletasks(); app.update()
t0 = time.perf_counter()
for _ in range(3):
    app.update()
print("baseline 3 updates: %.1f ms" % ((time.perf_counter()-t0)*1000))
for key in ("install", "mods", "settings", "home"):
    t = time.perf_counter()
    app.show_page(key)
    app.update_idletasks()
    d1 = (time.perf_counter()-t)*1000
    t = time.perf_counter()
    app.update()
    d2 = (time.perf_counter()-t)*1000
    print("%-9s show=%6.1f ms  draw=%6.1f ms" % (key, d1, d2))
print("widgets:", len(app.winfo_children()), "pages:", list(app._pages))
app.destroy()
