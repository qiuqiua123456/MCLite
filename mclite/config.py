"""配置持久化。配置存放在 %APPDATA%\\MCLite\\config.json。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------- 默认路径

def _appdata_dir() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / "MCLite"
    return Path.home() / ".mclite"


CONFIG_DIR = _appdata_dir()
CONFIG_FILE = CONFIG_DIR / "config.json"


def guess_minecraft_dir() -> Path:
    """猜测一个已存在的 .minecraft 目录，找不到就返回 %APPDATA%\\.minecraft。"""
    candidates = [
        Path(os.environ.get("APPDATA", "")) / ".minecraft",
        Path.home() / "AppData" / "Roaming" / ".minecraft",
    ]
    # 常见启动器目录
    if sys.platform == "win32":
        for drive in ("C:", "D:", "E:", "F:", "G:", "H:"):
            candidates.append(Path(drive + "\\") / ".minecraft")
            candidates.append(Path(drive + "\\") / "mc" / "versions" / ".minecraft")
            candidates.append(Path(drive + "\\") / "Games" / ".minecraft")
    for c in candidates:
        try:
            if c.is_dir() and (c / "versions").is_dir():
                return c
        except OSError:
            continue
    return Path(os.environ.get("APPDATA", str(Path.home()))) / ".minecraft"


DEFAULTS: dict[str, Any] = {
    "game_dir": "",
    "java_path": "",
    "memory_mb": 4096,
    "username": "Steve",
    "uuid": "",
    "access_token": "",
    "user_type": "legacy",
    # 国内直连 Mojang 基本拉不动（会话被掐），默认走 BMCLAPI 镜像
    "download_source": "bmclapi",   # official | bmclapi
    "download_threads": 16,
    "close_after_launch": False,
    "jvm_args": "",
    "fullscreen": False,
    "show_console": False,
    "window_width": 900,
    "window_height": 560,
    "ms_account": {},               # 微软正版账户（MsAccount.to_dict()）
    "accounts": [],                 # 多账号列表（accounts.Account.to_dict()）
    "current_account": 0,           # 当前账号在 accounts 里的下标，-1 表示无
    "theme": "pcl",                 # pcl | dark | light | midnight | forest
    "separate_instances": True,     # 每个版本独立游戏目录（隔离 mods / 存档）；整合包始终隔离
    "auto_java": True,              # 启动时缺 Java 自动下载
    "recent_dirs": [],              # 最近用过的游戏目录（最新的在前）
}


class Config:
    """极简配置对象：读时回落到默认值，写时立即落盘。"""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or CONFIG_FILE
        self._data: dict[str, Any] = dict(DEFAULTS)
        self.load()

    # ------------------------------------------------------------ 读写

    def load(self) -> None:
        try:
            if self.path.is_file():
                with open(self.path, "r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                if isinstance(raw, dict):
                    for k, v in raw.items():
                        if k in DEFAULTS:
                            self._data[k] = v
        except (OSError, ValueError):
            pass
        if not self._data.get("game_dir"):
            self._data["game_dir"] = str(guess_minecraft_dir())

    def save(self) -> None:
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except OSError:
            pass

    # ------------------------------------------------------------ 访问

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, DEFAULTS.get(key, default))

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def update(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            if k in DEFAULTS:
                self._data[k] = v
        self.save()

    # ------------------------------------------------------------ 便捷属性

    @property
    def game_dir(self) -> Path:
        return Path(self._data.get("game_dir") or guess_minecraft_dir())

    @game_dir.setter
    def game_dir(self, value: str | Path) -> None:
        self._data["game_dir"] = str(value)

    @property
    def versions_dir(self) -> Path:
        return self.game_dir / "versions"

    @property
    def libraries_dir(self) -> Path:
        return self.game_dir / "libraries"

    @property
    def assets_dir(self) -> Path:
        return self.game_dir / "assets"
