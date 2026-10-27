"""探测 BMCLAPI 的 Forge 安装器快速下载端点。"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")
from mclite.downloader import curl_fetch, fetch_text

d = json.loads(fetch_text("https://bmclapi2.bangbang93.com/forge/minecraft/1.20.1", timeout=20))
print("条数", len(d))
e = [x for x in d if x.get("version") == "47.4.28"]
print("element keys:", list(e[0].keys()) if e else "none")
if e:
    print(json.dumps(e[0], ensure_ascii=False)[:500])
if e and e[0].get("build"):
    url = "https://bmclapi2.bangbang93.com/forge/download/" + str(e[0]["build"])
    p = Path(r"C:\Users\qiu\AppData\Local\Temp\mclite_probe\inst_fast.jar")
    t = time.time()
    ok = curl_fetch(url, p, timeout=90)
    size = p.stat().st_size if p.exists() else 0
    print("fast url", url, ok, f"{time.time() - t:.1f}s", size)
