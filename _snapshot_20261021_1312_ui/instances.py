"""实例隔离：每个游戏版本使用自己独立的游戏目录。

隔离后 ``<游戏目录>/versions/<版本>/`` 本身就充当一个 ``.minecraft``：
mods、存档、资源包、光影、配置、日志都放在里面，不同版本互不干扰。
库和资源（libraries / assets）仍然共用游戏目录下的那两份，不重复占空间。
"""

from __future__ import annotations

from pathlib import Path

#: 隔离实例里会用到、启动前顺手建好的子目录
INSTANCE_SUBDIRS = ("mods", "saves", "resourcepacks", "shaderpacks", "config", "logs", "screenshots")


def instance_dir(game_dir: Path, version_id: str) -> Path:
    """某个版本的隔离目录（不一定存在）。"""
    return Path(game_dir) / "versions" / version_id


def game_dir_for(game_dir: Path, version_id: str, separate: bool = True) -> Path:
    """启动这个版本时该用的 ``--gameDir``。"""
    if separate and version_id:
        return instance_dir(game_dir, version_id)
    return Path(game_dir)


def mods_dir_for(game_dir: Path, version_id: str, separate: bool = True) -> Path:
    """这个版本实际的 mods 目录。"""
    if separate and version_id:
        return instance_dir(game_dir, version_id) / "mods"
    return Path(game_dir) / "mods"


def ensure_instance(path: Path) -> Path:
    """建好隔离实例的常用子目录，返回该路径。"""
    for name in INSTANCE_SUBDIRS:
        try:
            (path / name).mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
    return path


def is_isolated(game_dir: Path, version_id: str) -> bool:
    """这个版本目录里是否已经放了实例内容（用于列表里打个标记）。"""
    d = instance_dir(game_dir, version_id)
    for name in INSTANCE_SUBDIRS:
        try:
            if (d / name).is_dir():
                return True
        except OSError:
            continue
    return False


def effective(game_dir: Path, version_id: str, separate: bool = False) -> bool:
    """这个版本到底要不要隔离。

    三种情况会隔离：
    1. 设置里全局打开了「版本隔离」；
    2. 版本目录里已经躺着 mods / 存档 / 配置（PCL、HMCL 这类启动器留下的隔离实例，
       不隔离就等于把它的 mod 全丢了）；
    3. 调用方另有限定（比如整合包永远隔离）。
    """
    if not version_id:
        return bool(separate)
    return bool(separate) or is_isolated(game_dir, version_id)


def shared_mods(game_dir: Path) -> Path:
    """共用 mods 目录（不隔离时用）。"""
    return Path(game_dir) / "mods"
