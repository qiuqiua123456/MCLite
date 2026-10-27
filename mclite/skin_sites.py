"""第三方皮肤站（Yggdrasil / authlib-injector）登录。

Minecraft 的皮肤系统只认 Mojang 官方会话服务，第三方皮肤站的做法是
用 ``authlib-injector`` 这个 javaagent 在运行时把会话服务地址替换成皮肤站的
Yggdrasil API。所以这里要做两件事：

1. 用 Yggdrasil 协议（``/authserver/authenticate``）拿到皮肤站的
   ``accessToken`` 与角色 UUID；
2. 启动游戏时加 ``-javaagent:authlib-injector.jar=<API 根地址>``。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
import uuid as _uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .downloader import USER_AGENT, curl_fetch, fetch_bytes_robust

#: authlib-injector 的下载地址候选（BMCLAPI 镜像优先，官方兜底）
INJECTOR_META_URLS = (
    "https://bmclapi2.bangbang93.com/mirrors/authlib-injector/artifact/latest.json",
    "https://authlib-injector.yushi.moe/artifact/latest.json",
)

#: 内置的皮肤站
SITES: list["Site"] = []


class SkinError(Exception):
    def __init__(self, message: str, code: str = "") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Site:
    id: str
    name: str
    api: str
    homepage: str
    register_url: str = ""
    note: str = ""

    @property
    def auth_url(self) -> str:
        """浏览器里打开就能登录 / 注册的页面。"""
        return self.register_url or self.homepage


SITES = [
    Site(
        id="littleskin",
        name="LittleSkin",
        api="https://littleskin.cn/api/yggdrasil",
        homepage="https://littleskin.cn",
        register_url="https://littleskin.cn/auth/login",
        note="国内最常用的皮肤站，支持皮肤 / 披风",
    ),
    Site(
        id="mua",
        name="MUA 皮肤站",
        api="https://skin.mualliance.cn/api/yggdrasil",
        homepage="https://skin.mualliance.cn",
        register_url="https://skin.mualliance.cn/auth/login",
        note="MUA 用户中心（原 skin.mualliance.la 已失效）",
    ),
    Site(
        id="blessing",
        name="Blessing Skin",
        api="https://skin.prinzeugen.net/api/yggdrasil",
        homepage="https://skin.prinzeugen.net",
        register_url="https://skin.prinzeugen.net/auth/login",
        note="Blessing Skin 官方演示站",
    ),
]

SITE_BY_ID = {s.id: s for s in SITES}

#: 允许用户手填的自定义站点（本站就是一个标准 Yggdrasil API 根）
CUSTOM_ID = "custom"


@dataclass
class SkinAccount:
    name: str = ""
    uuid: str = ""
    access_token: str = ""
    api: str = ""
    site_id: str = ""
    client_token: str = ""

    @property
    def site_name(self) -> str:
        site = SITE_BY_ID.get(self.site_id)
        if site is not None:
            return site.name
        if self.api:
            host = urllib.parse.urlsplit(self.api).netloc
            return host or "第三方皮肤站"
        return "第三方皮肤站"


def _api_root(api: str) -> str:
    return (api or "").strip().rstrip("/")


def _post(url: str, payload: dict, timeout: int = 25) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            data = json.loads(exc.read().decode("utf-8", "replace"))
            detail = str(data.get("errorMessage") or data.get("message") or "")
        except Exception:                            # noqa: BLE001
            detail = ""
        if exc.code in (401, 403):
            raise SkinError(detail or "邮箱或密码不正确", "bad_credentials") from exc
        raise SkinError(detail or f"服务器返回 HTTP {exc.code}", f"http_{exc.code}") from exc
    except urllib.error.URLError as exc:
        raise SkinError(f"连不上皮肤站：{exc.reason}", "network") from exc
    except OSError as exc:
        raise SkinError(f"连不上皮肤站：{exc}", "network") from exc
    try:
        data = json.loads(raw.decode("utf-8", "replace"))
    except ValueError as exc:
        raise SkinError("皮肤站返回的不是合法 JSON", "bad_response") from exc
    if not isinstance(data, dict):
        raise SkinError("皮肤站返回格式异常", "bad_response")
    return data


def _norm_uuid(raw: str) -> str:
    """Yggdrasil 的 id 是 32 位无横线 UUID。"""
    text = (raw or "").replace("-", "").strip().lower()
    if len(text) == 32:
        try:
            return str(_uuid.UUID(text))
        except ValueError:
            return text
    return text


def authenticate(site: Site, email: str, password: str,
                 client_token: str = "") -> SkinAccount:
    """用邮箱 / 密码登录皮肤站，返回账号。"""
    email = (email or "").strip()
    if not email or not password:
        raise SkinError("请填写邮箱和密码", "empty")
    api = _api_root(site.api if isinstance(site, Site) else str(site))
    token = client_token or str(_uuid.uuid4())
    data = _post(f"{api}/authserver/authenticate", {
        "agent": {"name": "Minecraft", "version": 1},
        "username": email,
        "password": password,
        "clientToken": token,
        "requestUser": False,
    })
    access = str(data.get("accessToken") or "")
    if not access:
        raise SkinError("皮肤站没有返回 accessToken", "bad_response")
    profile = data.get("selectedProfile") or {}
    profiles = data.get("availableProfiles") or []
    if not profile and profiles:
        profile = profiles[0]
    if not profile:
        raise SkinError("这个账号还没有创建 Minecraft 角色，请先去皮肤站创建角色", "no_profile")
    return SkinAccount(
        name=str(profile.get("name") or email),
        uuid=_norm_uuid(str(profile.get("id") or "")),
        access_token=access,
        api=api,
        site_id=site.id if isinstance(site, Site) else CUSTOM_ID,
        client_token=token,
    )


def refresh(account: SkinAccount) -> SkinAccount:
    """用 accessToken 续期（皮肤站的令牌一般不会过期，失败就原样返回）。"""
    api = _api_root(account.api)
    if not api or not account.access_token:
        return account
    try:
        data = _post(f"{api}/authserver/refresh", {
            "accessToken": account.access_token,
            "clientToken": account.client_token or "",
            "requestUser": False,
        })
    except SkinError:
        return account
    access = str(data.get("accessToken") or "")
    if access:
        account.access_token = access
    return account


def custom_site(api: str, name: str = "") -> Site:
    """用户手填的 Yggdrasil API 根地址。"""
    api = _api_root(api)
    if not api.startswith(("http://", "https://")):
        raise SkinError("皮肤站地址要以 http:// 或 https:// 开头", "bad_url")
    host = urllib.parse.urlsplit(api).netloc or api
    return Site(id=CUSTOM_ID, name=name or host, api=api,
                homepage=f"https://{host}", register_url=f"https://{host}/auth/login")


def download_injector(game_dir: Path, on_log: Callable[[str], None] = lambda _m: None) -> Path:
    """下载 authlib-injector，返回 jar 路径（已存在就直接复用）。"""
    game_dir = Path(game_dir)
    out_dir = game_dir / "libraries" / "mclite" / "authlib-injector"
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("authlib-injector-*.jar"):
        if old.stat().st_size > 0:
            return old

    meta = None
    for url in INJECTOR_META_URLS:
        try:
            raw = fetch_bytes_robust(url, timeout=30, attempts=1)
            meta = json.loads(raw.decode("utf-8", "replace"))
            break
        except Exception:                            # noqa: BLE001
            continue
    if not isinstance(meta, dict):
        raise SkinError("下载 authlib-injector 失败（拿不到版本信息）", "network")

    version = str(meta.get("version") or "").strip()
    download = str(meta.get("download_url") or "").strip()
    if not download:
        raise SkinError("authlib-injector 的版本信息里没有下载地址", "bad_response")

    dest = out_dir / f"authlib-injector-{version or 'latest'}.jar"
    on_log(f"下载 authlib-injector {version} …")
    if curl_fetch(download, dest, timeout=120, retries=2, on_log=on_log):
        if dest.is_file() and dest.stat().st_size > 0:
            return dest
    raise SkinError("下载 authlib-injector 失败", "network")


def javaagent(account: SkinAccount, jar: Path) -> str:
    """拼出 ``-javaagent:...=<API>`` 参数。"""
    return f"-javaagent:{jar}={_api_root(account.api)}"


def open_auth_page(site: Site) -> str:
    """在浏览器里打开皮肤站的登录 / 注册页，返回打开的地址。"""
    import os
    import webbrowser
    url = site.auth_url
    if os.environ.get("MCLITE_NO_BROWSER") == "1":   # 截图 / 自动化时别抢浏览器
        return url
    try:
        webbrowser.open(url)
    except Exception:                                # noqa: BLE001
        pass
    return url
