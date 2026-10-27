"""微软正版登录：OAuth 设备码 → Xbox Live → XSTS → Minecraft 服务。

整条链路（官方启动器也是这么走的）：

1. ``devicecode`` 拿用户码，让玩家在浏览器里输入；
2. 轮询 ``token`` 拿到微软 access_token / refresh_token；
3. ``user.auth.xboxlive.com`` 换 XBL 令牌；
4. ``xsts.auth.xboxlive.com`` 换 XSTS 令牌（这里会暴露"没建 Xbox 档案"等问题）；
5. ``api.minecraftservices.com/authentication/login_with_xbox`` 换 Minecraft 令牌；
6. ``/minecraft/profile`` 拿正版 ID 和皮肤信息。

refresh_token 有效期很长，Minecraft 令牌只有 24 小时，所以过期后
用 refresh_token 直接重走第 3~6 步即可，不需要再让玩家输入代码。
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable

USER_AGENT = "MCLite/1.0 (+https://localhost)"

# 公共客户端 ID（微软账号设备码流程，第三方启动器通用，无需 client secret）
CLIENT_ID = "fe72edc2-3a6f-4280-90e8-e2beb64ce7e1"
SCOPE = "XboxLive.signin offline_access"

DEVICE_CODE_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode"
TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
XBL_URL = "https://user.auth.xboxlive.com/user/authenticate"
XSTS_URL = "https://xsts.auth.xboxlive.com/xsts/authorize"
MC_LOGIN_URL = "https://api.minecraftservices.com/authentication/login_with_xbox"
MC_PROFILE_URL = "https://api.minecraftservices.com/minecraft/profile"

XSTS_ERRORS = {
    "2148916233": "这个微软账号还没创建 Xbox 档案，请先登录 xbox.com 建档",
    "2148916235": "你所在的地区不支持 Xbox Live",
    "2148916236": "该账号需要先在网页上完成成人身份验证",
    "2148916237": "该账号需要先在网页上完成成人身份验证",
    "2148916238": "未成年账号需要先加入一个微软家庭组才能登录",
    "2148916227": "该账号已被 Xbox Live 封禁",
}


class AuthError(Exception):
    """登录失败，message 直接给玩家看。code 是 OAuth 的 error 字段（如有）。"""

    def __init__(self, message: str, code: str = "") -> None:
        super().__init__(message)
        self.code = code


@dataclass
class DeviceLogin:
    user_code: str
    verification_uri: str
    device_code: str
    interval: int
    expires_in: int
    message: str = ""


@dataclass
class MsAccount:
    name: str
    uuid: str
    access_token: str        # Minecraft 令牌
    refresh_token: str       # 微软 refresh token
    expires_at: float = 0.0  # Minecraft 令牌到期时间（time.time()）

    @property
    def expired(self) -> bool:
        return time.time() > self.expires_at - 120

    def to_dict(self) -> dict:
        return {
            "name": self.name, "uuid": self.uuid,
            "access_token": self.access_token, "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MsAccount":
        return cls(
            name=str(d.get("name") or ""), uuid=str(d.get("uuid") or ""),
            access_token=str(d.get("access_token") or ""),
            refresh_token=str(d.get("refresh_token") or ""),
            expires_at=float(d.get("expires_at") or 0),
        )


# ---------------------------------------------------------------- HTTP

def _send(req: urllib.request.Request, timeout: int = 30,
          retries: int = 3) -> dict:
    """发请求：网络层失败重试几次，HTTP 错误翻译成 AuthError。"""
    last = ""
    for attempt in range(max(1, retries)):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            try:
                payload = json.loads(raw)
            except ValueError:
                payload = {"error": str(exc.code), "error_description": raw[:300]}
            payload.setdefault("error", str(exc.code))
            payload.setdefault("error_description", raw[:300])
            raise AuthError(str(payload["error_description"] or payload["error"]),
                            str(payload.get("error") or "")) from None
        except (urllib.error.URLError, OSError) as exc:
            last = str(getattr(exc, "reason", exc))
            if attempt + 1 < retries:
                time.sleep(1.5 * (attempt + 1))
    raise AuthError(f"连不上微软服务器，请检查网络或代理（{last[:60]}）")


def _request(url: str, data: dict | None = None, headers: dict | None = None,
             timeout: int = 30) -> dict:
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=body, headers=hdrs,
                                 method="POST" if data is not None else "GET")
    return _send(req, timeout)


def _form(url: str, data: dict, timeout: int = 30) -> dict:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded",
                 "Accept": "application/json"},
        method="POST")
    return _send(req, timeout)


# ---------------------------------------------------------------- 第 1~2 步

def begin() -> DeviceLogin:
    """申请一个设备码。"""
    payload = _form(DEVICE_CODE_URL, {"client_id": CLIENT_ID, "scope": SCOPE})
    return DeviceLogin(
        user_code=str(payload.get("user_code") or ""),
        verification_uri=str(payload.get("verification_uri") or "https://microsoft.com/link"),
        device_code=str(payload.get("device_code") or ""),
        interval=int(payload.get("interval") or 5),
        expires_in=int(payload.get("expires_in") or 900),
        message=str(payload.get("message") or ""),
    )


def wait_for_account(login: DeviceLogin,
                     on_status: Callable[[str], None] = lambda _m: None,
                     cancelled: Callable[[], bool] = lambda: False) -> MsAccount:
    """轮询直到玩家完成授权，然后走完整条认证链。"""
    interval = max(1, login.interval)
    deadline = time.time() + login.expires_in
    on_status("等待在浏览器中完成授权…")

    while time.time() < deadline:
        if cancelled():
            raise AuthError("已取消")
        time.sleep(interval)
        try:
            token = _form(TOKEN_URL, {
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "client_id": CLIENT_ID,
                "device_code": login.device_code,
            })
        except AuthError as exc:
            code = exc.code or ""
            if code in ("authorization_pending", "pending"):
                continue
            if code == "slow_down":
                interval += 5
                continue
            if code in ("expired_token", "code_expired", "bad_verification_code"):
                raise AuthError("授权码已过期，请重新登录", code) from None
            if code in ("authorization_declined", "access_denied"):
                raise AuthError("你在浏览器中拒绝了授权", code) from None
            raise
        return _finish(token)

    raise AuthError("等待授权超时，请重新登录")


def refresh(account: MsAccount,
            on_status: Callable[[str], None] = lambda _m: None) -> MsAccount:
    """用 refresh_token 续期（不打扰玩家）。"""
    if not account.refresh_token:
        raise AuthError("没有可用的刷新令牌，请重新登录")
    on_status("正在刷新登录状态…")
    try:
        token = _form(TOKEN_URL, {
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "refresh_token": account.refresh_token,
            "scope": SCOPE,
        })
    except AuthError as exc:
        raise AuthError(f"登录已过期，请重新登录（{exc}）") from None
    return _finish(token)


def _finish(token: dict) -> MsAccount:
    ms_access = str(token.get("access_token") or "")
    if not ms_access:
        raise AuthError("微软没有返回访问令牌")

    xbl, _ = _xbox(ms_access)
    xsts, uhs = _xsts(xbl)
    mc_token, expires_in = _mc_login(xsts, uhs)
    uuid_str, name = _profile(mc_token)

    return MsAccount(
        name=name,
        uuid=uuid_str,
        access_token=mc_token,
        refresh_token=str(token.get("refresh_token") or ""),
        expires_at=time.time() + float(expires_in or 86400),
    )


# ---------------------------------------------------------------- 第 3~6 步

def _xbox(ms_access: str) -> tuple[str, str]:
    payload = {
        "Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com",
                       "RpsTicket": f"d={ms_access}"},
        "RelyingParty": "http://auth.xboxlive.com",
        "TokenType": "JWT",
    }
    data = _request(XBL_URL, payload)
    token = str(data.get("Token") or "")
    if not token:
        raise AuthError("Xbox Live 认证失败：没有拿到令牌")
    uhs = ""
    try:
        uhs = data["DisplayClaims"]["xui"][0]["uhs"]
    except (KeyError, IndexError, TypeError):
        pass
    return token, uhs


def _xsts(xbl_token: str) -> tuple[str, str]:
    payload = {
        "Properties": {"SandboxId": "RETAIL", "UserTokens": [xbl_token]},
        "RelyingParty": "rp://api.minecraftservices.com/",
        "TokenType": "JWT",
    }
    try:
        data = _request(XSTS_URL, payload)
    except AuthError as exc:
        text = str(exc)
        for code, hint in XSTS_ERRORS.items():
            if code in text:
                raise AuthError(hint) from None
        raise AuthError(f"Xbox 授权失败：{text}") from None

    token = str(data.get("Token") or "")
    if not token:
        raise AuthError("Xbox 授权失败：没有拿到 XSTS 令牌")
    uhs = ""
    try:
        uhs = data["DisplayClaims"]["xui"][0]["uhs"]
    except (KeyError, IndexError, TypeError):
        pass
    return token, uhs


def _mc_login(xsts_token: str, uhs: str) -> tuple[str, int]:
    payload = {"identityToken": f"XBL3.0 x={uhs};{xsts_token}"}
    try:
        data = _request(MC_LOGIN_URL, payload)
    except AuthError as exc:
        msg = str(exc)
        if "401" in msg or "403" in msg:
            raise AuthError("这个账号没有 Minecraft: Java 版的所有权") from None
        raise AuthError(f"Minecraft 认证失败：{msg}") from None
    token = str(data.get("access_token") or "")
    if not token:
        raise AuthError("Minecraft 认证失败：没有拿到访问令牌")
    return token, int(data.get("expires_in") or 86400)


def _profile(mc_token: str) -> tuple[str, str]:
    data = _request(MC_PROFILE_URL, headers={"Authorization": f"Bearer {mc_token}"})
    uuid_str = str(data.get("id") or "")
    name = str(data.get("name") or "")
    if not uuid_str or not name:
        raise AuthError("拿不到正版档案，可能这个账号没有购买 Minecraft")
    return uuid_str, name
