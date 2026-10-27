"""多账号管理：正版（微软）与离线账号统一存放，支持保存、切换、删除、复制 UUID。

配置结构（`%APPDATA%\\MCLite\\config.json`）：

    "accounts": [{"kind": "msa", "name": "...", "uuid": "...", ...}, ...],
    "current_account": 0

老版本只有一个 `ms_account` 字段，`load()` 会自动迁移成列表。
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from .auth import MsAccount
from .launcher import offline_uuid


@dataclass
class Account:
    kind: str = "offline"          # msa / offline / yggdrasil
    name: str = ""
    uuid: str = ""
    access_token: str = ""
    refresh_token: str = ""
    expires_at: float = 0.0
    #: 第三方皮肤站（Yggdrasil）相关
    api: str = ""
    site_id: str = ""
    client_token: str = ""

    @property
    def premium(self) -> bool:
        return self.kind == "msa"

    @property
    def third_party(self) -> bool:
        return self.kind == "yggdrasil"

    @property
    def label(self) -> str:
        if self.premium:
            return "微软正版"
        if self.third_party:
            from .skin_sites import SITE_BY_ID
            site = SITE_BY_ID.get(self.site_id)
            return site.name if site else "第三方皮肤站"
        return "离线"

    @property
    def expired(self) -> bool:
        return self.premium and time.time() > self.expires_at - 120

    def short_uuid(self) -> str:
        u = self.uuid.replace("-", "")
        if len(u) == 32:
            return f"{u[:8]}-{u[8:12]}-{u[12:16]}-{u[16:20]}-{u[20:]}"
        return self.uuid

    def to_ms(self) -> MsAccount:
        return MsAccount(name=self.name, uuid=self.uuid, access_token=self.access_token,
                         refresh_token=self.refresh_token, expires_at=self.expires_at)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind, "name": self.name, "uuid": self.uuid,
            "access_token": self.access_token, "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "api": self.api, "site_id": self.site_id, "client_token": self.client_token,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "Account":
        return cls(
            kind=str(raw.get("kind") or "offline"),
            name=str(raw.get("name") or "Steve"),
            uuid=str(raw.get("uuid") or ""),
            access_token=str(raw.get("access_token") or ""),
            refresh_token=str(raw.get("refresh_token") or ""),
            expires_at=float(raw.get("expires_at") or 0.0),
            api=str(raw.get("api") or ""),
            site_id=str(raw.get("site_id") or ""),
            client_token=str(raw.get("client_token") or ""),
        )

    @classmethod
    def from_skin(cls, acc) -> "Account":
        """由 skin_sites.SkinAccount 转成账号。"""
        return cls(kind="yggdrasil", name=acc.name, uuid=acc.uuid,
                   access_token=acc.access_token, api=acc.api,
                   site_id=acc.site_id, client_token=acc.client_token)

    @classmethod
    def from_ms(cls, acc: MsAccount) -> "Account":
        return cls(kind="msa", name=acc.name, uuid=acc.uuid,
                   access_token=acc.access_token, refresh_token=acc.refresh_token,
                   expires_at=acc.expires_at)

    @classmethod
    def new_offline(cls, name: str) -> "Account":
        return cls(kind="offline", name=name, uuid=offline_uuid(name))


def load(cfg) -> list[Account]:
    """读出账号列表，并顺手把旧的单账号配置迁移过来。"""
    raw = cfg.get("accounts")
    out: list[Account] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and item.get("name"):
                out.append(Account.from_dict(item))
    if not out:
        legacy = cfg.get("ms_account") or {}
        if isinstance(legacy, dict) and legacy.get("refresh_token"):
            out.append(Account.from_ms(MsAccount.from_dict(legacy)))
    return out


def save(cfg, items: list[Account], index: int) -> None:
    cfg.set("accounts", [a.to_dict() for a in items])
    cfg.set("current_account", index)
    cfg.save()


def current_index(cfg, count: int) -> int:
    try:
        idx = int(cfg.get("current_account"))
    except (TypeError, ValueError):
        idx = 0
    if count <= 0:
        return -1
    return max(0, min(idx, count - 1))


def upsert(items: list[Account], acc: Account,
           make_current: bool = True) -> tuple[list[Account], int]:
    """同一个账号（按 uuid）只保留一份；返回新列表和它的下标。"""
    for i, old in enumerate(items):
        if acc.uuid and old.uuid and old.uuid == acc.uuid:
            items[i] = acc
            return items, i
    if not make_current:
        items.append(acc)
        return items, -1
    items.append(acc)
    return items, len(items) - 1


def remove(items: list[Account], index: int) -> tuple[list[Account], int]:
    if 0 <= index < len(items):
        items.pop(index)
    return items, (max(0, index - 1) if items else -1)
