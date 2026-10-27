"""整合包（Modrinth ``.mrpack``）导入：解包索引、装依赖版本、下模组、铺覆盖文件。

一个整合包会被装成**一个独立版本**：``versions/<包名>/<包名>.json``，
里面只写 ``inheritsFrom`` 指向它依赖的原版 / 加载器版本，
真正的 mods、config、存档都放在这个版本目录里（配合实例隔离天然互不干扰）。
"""

from __future__ import annotations

import json
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .downloader import DownloadTask, Downloader, human_size
from .installer import Installer
from .launcher import list_installed_versions
from . import loaders

INDEX_NAME = "modrinth.index.json"
OVERRIDE_DIRS = ("overrides", "client-overrides")

#: Modrinth 依赖字段 → 加载器种类
DEPENDENCY_KINDS = [
    ("fabric-loader", "fabric"),
    ("quilt-loader", "quilt"),
    ("neoforge", "neoforge"),
    ("forge", "forge"),
]

_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class PackError(Exception):
    pass


def _manifest_url(version_id: str) -> str | None:
    """从官方版本清单里查某个版本的 JSON 地址。"""
    from .downloader import fetch_json as _fj
    from .versionmeta import VERSION_MANIFEST, parse_manifest
    try:
        data = _fj(VERSION_MANIFEST, timeout=30)
        for v in parse_manifest(data):
            if v.id == version_id:
                return v.url
    except Exception:                                   # noqa: BLE001
        return None
    return None


@dataclass
class PackIndex:
    name: str = "整合包"
    version: str = ""
    mc_version: str = ""
    loader_kind: str = ""
    loader_version: str = ""
    files: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def label(self) -> str:
        return f"{self.name} {self.version}".strip()


def safe_name(name: str) -> str:
    """把整合包名变成合法的目录名（保留中文，去掉 Windows 非法字符）。"""
    text = _BAD_CHARS.sub("_", (name or "整合包").strip())
    text = text.strip(" .")
    return text[:60] or "整合包"


def read_index(path: Path) -> PackIndex:
    """读 ``modrinth.index.json``，解析名称 / 依赖 / 文件列表。"""
    path = Path(path)
    if not path.is_file():
        raise PackError(f"文件不存在：{path}")
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            if INDEX_NAME not in names:
                raise PackError(
                    "这不是 Modrinth 整合包（压缩包里没有 modrinth.index.json）。"
                    "目前只支持 .mrpack 格式。")
            raw = zf.read(INDEX_NAME)
    except zipfile.BadZipFile as exc:
        raise PackError("压缩包损坏或不是 zip 文件") from exc
    except OSError as exc:
        raise PackError(f"打不开整合包：{exc}") from exc

    try:
        data = json.loads(raw.decode("utf-8", "replace"))
    except ValueError as exc:
        raise PackError("modrinth.index.json 不是合法 JSON") from exc
    if not isinstance(data, dict):
        raise PackError("modrinth.index.json 格式异常")

    deps = data.get("dependencies") or {}
    if not isinstance(deps, dict):
        deps = {}
    mc = str(deps.get("minecraft") or "")
    if not mc:
        raise PackError("整合包没有声明 Minecraft 版本")
    kind = ""
    ver = ""
    for key, k in DEPENDENCY_KINDS:
        if key in deps:
            kind, ver = k, str(deps.get(key) or "")
            break

    files = [f for f in (data.get("files") or []) if isinstance(f, dict)]
    return PackIndex(
        name=str(data.get("name") or path.stem),
        version=str(data.get("versionId") or ""),
        mc_version=mc,
        loader_kind=kind,
        loader_version=ver,
        files=files,
        summary=str(data.get("summary") or ""),
    )


def _client_files(index: PackIndex) -> list[dict[str, Any]]:
    """过滤掉服务端专用文件。"""
    out = []
    for f in index.files:
        env = f.get("env") or {}
        if isinstance(env, dict) and str(env.get("client") or "") == "unsupported":
            continue
        if f.get("path") and (f.get("downloads") or []):
            out.append(f)
    return out


def _write_version_json(version_dir: Path, pack_id: str, parent: str) -> Path:
    payload = {
        "id": pack_id,
        "inheritsFrom": parent,
        "type": "release",
        "mclite": {"modpack": True},
    }
    version_dir.mkdir(parents=True, exist_ok=True)
    dest = version_dir / f"{pack_id}.json"
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return dest


def _extract_overrides(path: Path, version_dir: Path,
                       on_log: Callable[[str], None], cancel: Callable[[], bool] | None) -> int:
    count = 0
    try:
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                name = info.filename.replace("\\", "/")
                for prefix in OVERRIDE_DIRS:
                    if not name.startswith(prefix + "/"):
                        continue
                    rel = name[len(prefix) + 1:]
                    if not rel or info.is_dir():
                        break
                    if name.endswith("/"):
                        break
                    if cancel and cancel():
                        raise PackError("用户取消")
                    dest = version_dir / rel
                    try:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(info) as src, open(dest, "wb") as out:
                            shutil.copyfileobj(src, out)
                        count += 1
                    except OSError:
                        continue
                    break
    except zipfile.BadZipFile:
        return count
    if count:
        on_log(f"解出覆盖文件 {count} 个")
    return count


def install(
    path: Path,
    game_dir: Path,
    java: Any = None,
    on_log: Callable[[str], None] = lambda _m: None,
    progress_cb: Callable | None = None,
    cancel: Callable[[], bool] | None = None,
    threads: int = 16,
) -> str:
    """导入整合包，返回装好的版本 id。"""
    game_dir = Path(game_dir)
    index = read_index(path)
    on_log(f"整合包：{index.label}（Minecraft {index.mc_version}"
           f"{'，' + index.loader_kind + ' ' + index.loader_version if index.loader_kind else ''}）")

    # 1. 原版
    installed = set(list_installed_versions(game_dir))
    if index.mc_version not in installed:
        on_log(f"缺少原版 {index.mc_version}，先安装…")
        url = _manifest_url(index.mc_version)
        if not url:
            raise PackError(f"版本清单里找不到 {index.mc_version}")
        inst = Installer(game_dir, source="official", threads=threads, log=on_log)
        ok, msg = inst.install(index.mc_version, url, progress_cb=progress_cb)
        if not ok:
            raise PackError(f"原版 {index.mc_version} 安装失败：{msg}")
    else:
        on_log(f"原版 {index.mc_version} 已存在")

    # 2. 加载器
    parent = index.mc_version
    if index.loader_kind and index.loader_version:
        have = loaders.installed_loader_versions(game_dir)
        target = None
        for vid in have:
            if index.loader_version in vid and index.mc_version in vid:
                if loaders.loader_complete(game_dir, vid):
                    target = vid
                    break
                on_log(f"加载器 {vid} 不完整，重新安装")
        if target:
            parent = target
            on_log(f"加载器已存在：{target}")
        else:
            if java is None:
                from .java import detect_all, pick_for_version
                from .javaauto import find_or_install
                need = 17
                try:
                    from .launcher import version_meta
                    need = int((version_meta(game_dir, index.mc_version).get("javaVersion") or 17))
                except Exception:                # noqa: BLE001
                    need = 17
                java = find_or_install(game_dir, need, detect_all(game_dir),
                                       on_log=on_log, progress_cb=progress_cb)
            on_log(f"安装加载器 {index.loader_kind} {index.loader_version} …")
            parent = loaders.install(
                index.loader_kind, index.mc_version, index.loader_version,
                game_dir, java, on_log=on_log, cancel=cancel)

    # 3. 包目录 + 版本 JSON
    pack_id = safe_name(index.name)
    version_dir = game_dir / "versions" / pack_id
    _write_version_json(version_dir, pack_id, parent)
    on_log(f"创建实例版本：{pack_id}（继承 {parent}）")

    # 4. 覆盖文件
    _extract_overrides(Path(path), version_dir, on_log, cancel)

    # 5. 模组文件
    files = _client_files(index)
    tasks: list[DownloadTask] = []
    for f in files:
        rel = str(f.get("path") or "")
        urls = [str(u) for u in (f.get("downloads") or []) if u]
        if not rel or not urls:
            continue
        target = version_dir / rel
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
        hashes = f.get("hashes") or {}
        tasks.append(DownloadTask(
            url=urls[0],
            dest=target,
            sha1=hashes.get("sha1") or None,
            size=int(f.get("fileSize") or 0) or None,
        ))
    if tasks:
        total = sum(t.size or 0 for t in tasks)
        on_log(f"下载整合包内容：{len(tasks)} 个文件（{human_size(total)}）")
        dl = Downloader(threads=max(2, threads))
        ok, bad = dl.run(tasks, source="official", progress_cb=progress_cb, on_log=on_log)
        if bad:
            on_log(f"有 {bad} 个文件下载失败，可重试导入（已下载的会跳过）")
    else:
        on_log("整合包里没有需要下载的模组文件")

    on_log(f"整合包导入完成：{pack_id}")
    return pack_id


def is_pack(game_dir: Path, version_id: str) -> bool:
    """某个版本是不是整合包（版本 JSON 带 ``mclite.modpack`` 标记）。"""
    d = Path(game_dir) / "versions" / version_id
    for js in d.glob("*.json") if d.is_dir() else ():
        try:
            with open(js, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and (data.get("mclite") or {}).get("modpack"):
            return True
    return False


def list_packs(game_dir: Path) -> list[str]:
    """已导入的整合包版本 id（版本 JSON 里带 mclite.modpack 标记）。"""
    out: list[str] = []
    vdir = Path(game_dir) / "versions"
    if not vdir.is_dir():
        return out
    try:
        for d in vdir.iterdir():
            if not d.is_dir():
                continue
            for js in d.glob("*.json"):
                try:
                    with open(js, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                except (OSError, ValueError):
                    continue
                if isinstance(data, dict) and (data.get("mclite") or {}).get("modpack"):
                    out.append(d.name)
                    break
    except OSError:
        pass
    return out
