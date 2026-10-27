import sys, time, cProfile, pstats, io
sys.path.insert(0, r"F:\MCLite")
from mclite.ui.app import App
app = App(); app.create_pages()
for _ in range(3):
    app.update_idletasks(); app.update()
app.show_page("home"); app.update()
pr = cProfile.Profile()
pr.enable()
for _ in range(4):
    app.show_page("mods"); app.update()
    app.show_page("home"); app.update()
pr.disable()
s = io.StringIO()
pstats.Stats(pr, stream=s).sort_stats("cumulative").print_stats(22)
print(s.getvalue())
app.destroy()
