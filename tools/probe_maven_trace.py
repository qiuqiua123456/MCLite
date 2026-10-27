"""追踪 BMCLAPI maven 的跳转链，看它到底把文件重定向到哪。"""

from __future__ import annotations

import http.client
import ssl
import socket
import time
import urllib.request
from urllib.parse import urlparse


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        print(f"  -> {code} Location: {newurl}")
        return None


opener = urllib.request.build_opener(NoRedirect)
URL = "https://bmclapi2.bangbang93.com/maven/org/spongepowered/mixin/0.8.5/mixin-0.8.5.jar"
print("请求:", URL)
try:
    r = opener.open(urllib.request.Request(URL, headers={"User-Agent": "MCLite/1.0"}), timeout=20)
    print("状态:", r.status, "长度:", r.headers.get("Content-Length"))
except Exception as exc:                                 # noqa: BLE001
    print("异常:", type(exc).__name__, str(exc)[:120])

print("\n=== 直连重试 4 次，看 TLS 握手是否稳定 ===")
for i in range(4):
    t0 = time.time()
    try:
        req = urllib.request.Request(URL, headers={"User-Agent": "MCLite/1.0", "Range": "bytes=0-1023"})
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read()
        print(f"  第{i+1}次 OK   {time.time()-t0:5.1f}s  {r.status}  {len(body)} B")
    except Exception as exc:                             # noqa: BLE001
        print(f"  第{i+1}次 FAIL {time.time()-t0:5.1f}s  {type(exc).__name__}: {str(exc)[:60]}")
    time.sleep(1.0)

print("\n=== DNS 解析 ===")
for host in ("bmclapi2.bangbang93.com", "maven.minecraftforge.net"):
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
        print(f"  {host}: {sorted({ai[4][0] for ai in infos})}")
    except Exception as exc:                             # noqa: BLE001
        print(f"  {host}: FAIL {exc}")
