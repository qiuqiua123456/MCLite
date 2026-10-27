"""皮肤与头像：从会话服务器拿皮肤纹理，顺便支持上传皮肤。

头像不依赖 Pillow：Tk 8.6 的 photo image 自带 `copy -from -zoom`，
可以在画布上直接把皮肤图里 (8,8)-(16,16) 那块"脸"抠出来放大。
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request

USER_AGENT = "MCLite/1.3 (skin)"
MOJANG_SESSION = "https://sessionserver.mojang.com/session/minecraft/profile/{uuid}"
MOJANG_SKIN_API = "https://api.minecraftservices.com/minecraft/profile/skins"
TEXTURE_HOST = "http://textures.minecraft.net/texture/"


class SkinError(Exception):
    def __init__(self, message: str, code: str = ""):
        super().__init__(message)
        self.message = message
        self.code = code


def _get(url: str, timeout: int = 15) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise SkinError("没有找到这个玩家的皮肤资料", "not_found") from exc
        if exc.code == 204:
            raise SkinError("这个账号还没有设置皮肤", "empty") from exc
        raise SkinError(f"皮肤服务器返回 {exc.code}", "http") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise SkinError(f"连不上皮肤服务器：{exc}", "network") from exc


def session_url(uuid: str, api: str = "") -> str:
    """微软账号用官方会话服务器；皮肤站用自己的 Yggdrasil 根。"""
    if api:
        return f"{api.rstrip('/')}/sessionserver/session/minecraft/profile/{uuid}"
    return MOJANG_SESSION.format(uuid=uuid)


def profile(uuid: str, api: str = "", timeout: int = 15) -> dict:
    """读会话服务器资料，返回 {name, uuid, skin, cape, model}。"""
    if not uuid:
        raise SkinError("这个账号没有 UUID", "no_uuid")
    raw = _get(session_url(uuid.replace("-", ""), api), timeout=timeout)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SkinError("皮肤资料解析失败", "bad_json") from exc
    out = {"name": data.get("name", ""), "uuid": data.get("id", ""),
           "skin": "", "cape": "", "model": "classic"}
    for prop in data.get("properties") or []:
        if prop.get("name") != "textures":
            continue
        try:
            payload = base64.b64decode(prop.get("value", "") + "==").decode("utf-8")
            textures = json.loads(payload).get("textures") or {}
        except Exception:                       # noqa: BLE001 - 格式再怪也不该崩
            continue
        skin = textures.get("SKIN") or {}
        cape = textures.get("CAPE") or {}
        out["skin"] = skin.get("url", "")
        out["cape"] = cape.get("url", "")
        out["model"] = "slim" if (skin.get("metadata") or {}).get("model") == "slim" else "classic"
    return out


def skin_image(url: str, timeout: int = 20) -> bytes:
    """下载皮肤原图（64x64 或 64x32 的 PNG 字节）。"""
    if not url:
        raise SkinError("没有皮肤地址", "empty")
    if url.startswith("http://textures.minecraft.net"):
        url = "https://" + url[len("http://"):]
    return _get(url, timeout=timeout)


def head_bytes(raw_profile: dict) -> bytes:
    """资料 → 皮肤 PNG 字节（头像由 UI 侧裁剪）。"""
    return skin_image(str(raw_profile.get("skin") or ""))


def _multipart(fields: dict, files: dict) -> tuple[bytes, str]:
    """极简 multipart/form-data 编码。"""
    boundary = "----MCLiteForm7d91f2"
    out = bytearray()
    for key, value in fields.items():
        out += f"--{boundary}\r\n".encode()
        out += f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode()
        out += f"{value}\r\n".encode()
    for key, (filename, blob) in files.items():
        out += f"--{boundary}\r\n".encode()
        out += (f'Content-Disposition: form-data; name="{key}"; '
                f'filename="{filename}"\r\n').encode()
        out += b"Content-Type: image/png\r\n\r\n"
        out += blob
        out += b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def upload(uuid: str, token: str, png: bytes, variant: str = "classic",
           timeout: int = 60) -> None:
    """上传正版账号皮肤（微软 API）。"""
    if not token:
        raise SkinError("没有可用的登录令牌", "no_token")
    if not png.startswith(b"\x89PNG"):
        raise SkinError("皮肤必须是 PNG 图片", "bad_format")
    body, ctype = _multipart({"variant": variant}, {"file": ("skin.png", png)})
    req = urllib.request.Request(MOJANG_SKIN_API, data=body, method="POST", headers={
        "User-Agent": USER_AGENT,
        "Authorization": f"Bearer {token}",
        "Content-Type": ctype,
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise SkinError("登录已过期，请重新登录微软账号", "unauthorized") from exc
        if exc.code == 400:
            raise SkinError("皮肤不符合要求（64x64 或 64x32 的 PNG）", "bad_skin") from exc
        raise SkinError(f"上传失败（HTTP {exc.code}）", "http") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise SkinError(f"连不上皮肤服务器：{exc}", "network") from exc


def reset(uuid: str, token: str, timeout: int = 30) -> None:
    """删掉当前皮肤，恢复默认。"""
    req = urllib.request.Request(MOJANG_SKIN_API, data=b"", method="DELETE", headers={
        "User-Agent": USER_AGENT,
        "Authorization": f"Bearer {token}",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
    except urllib.error.HTTPError as exc:
        raise SkinError(f"操作失败（HTTP {exc.code}）", "http") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise SkinError(f"连不上皮肤服务器：{exc}", "network") from exc


def fetch_skin_png(uuid: str, api: str = "") -> bytes | None:
    """给 UI 用：失败不抛异常，直接返回 None。"""
    try:
        return head_bytes(profile(uuid, api))
    except SkinError:
        return None
