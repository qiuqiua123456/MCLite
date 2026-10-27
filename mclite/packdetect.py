"""整合包格式识别与统一安装入口。

支持四种来源（拖进来就能装）：

* ``.mrpack`` / 带 ``modrinth.index.json`` 的 zip —— Modrinth 格式；
* 带 ``manifest.json`` 的 zip —— CurseForge 格式；
* 带 ``mmc-pack.json`` 的 zip —— MultiMC / Prism 格式；
* 其余 zip —— 当作"散装整合包"：整包解到实例目录，继承用户当前选择的版本。

单文件 ``.jar`` 不在这里处理（那是 Mod 安装）。
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import curseforge, loaders, modpack
from .downloader import DownloadTask, Downloader, human_size
from .installer import Installer
from .launcher import list_installed_versions

INDEX_NAME = modpack.INDEX_NAME
MMC_NAME = "mmc-pack.json"
CF_NAME = "manifest.json"


class PackFormatError(Exception):
    pass


@dataclass
class PackInfo:
    kind: str = "unknown"           # mrpack / curseforge / multimc / plain / mod / unknown
    name: str = ""
    mc_version: str = ""
    loader_kind: str = ""
    loader_version: str = ""
    files: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    cf_files: list[dict] = field(default_factory=list)

    @property
    def label(self) -> str:
        return {
            "mrpack": "Modrinth 整合包",
            "curseforge": "CurseForge 整合包",
            "multimc": "MultiMC 整合包",
            "plain": "压缩包（按散装整合包处理）",
            "mod": "Mod",
        }.get(self.kind, "未知格式")

    @property
    def installable(self) -> bool:
        return self.kind in ("mrpack", "curseforge", "multimc", "plain")


def _read_json_from_zip(zf: zipfile.ZipFile, name: str) -> dict | None:
    try:
        raw = zf.read(name)
    except KeyError:
        return None
    try:
        data = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def detect(path: Path) -> PackInfo:
    """只看压缩包结构判断格式，不联网。"""
    path = Path(path)
    if path.suffix.lower() == ".jar":
        return PackInfo(kind="mod", name=path.stem)
    if not path.is_file():
        raise PackFormatError(f"文件不存在：{path}")
    if path.suffix.lower() not in (".zip", ".mrpack", ".mcpack", ".rar", ".7z"):
        raise PackFormatError(f"不认识的格式：{path.suffix or '无扩展名'}")

    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            lower = {n.lower() for n in names}
            if INDEX_NAME in names:
                idx = modpack.read_index(path)
                return PackInfo(kind="mrpack", name=idx.label, mc_version=idx.mc_version,
                                loader_kind=idx.loader_kind,
                                loader_version=idx.loader_version,
                                files=[str(f.get("path") or "") for f in idx.files])
            if MMC_NAME in names:
                data = _read_json_from_zip(zf, MMC_NAME) or {}
                return _parse_mmc(path, data)
            if CF_NAME in names:
                data = _read_json_from_zip(zf, CF_NAME) or {}
                return _parse_curseforge(path, data, names)
            mods = [n for n in names if n.lower().startswith(("mods/", "minecraft/mods/"))
                    and n.lower().endswith(".jar")]
            if mods:
                return PackInfo(kind="plain", name=path.stem, files=mods[:1],
                                notes=[f"包内有 {len(mods)} 个 Mod"])
            if any(n.lower().endswith(".jar") for n in names):
                return PackInfo(kind="plain", name=path.stem)
            raise PackFormatError("压缩包里没有找到任何整合包标志（modrinth.index.json / "
                                  "manifest.json / mmc-pack.json / mods 目录）")
    except zipfile.BadZipFile as exc:
        raise PackFormatError("压缩包损坏，或者不是 zip 格式（rar/7z 请先解压）") from exc
    except OSError as exc:
        raise PackFormatError(f"打不开压缩包：{exc}") from exc


def _parse_mmc(path: Path, data: dict) -> PackInfo:
    info = PackInfo(kind="multimc", name=str(data.get("name") or path.stem))
    for comp in data.get("components") or []:
        if not isinstance(comp, dict):
            continue
        uid = str(comp.get("uid") or "").lower()
        ver = str(comp.get("version") or "")
        if uid == "net.minecraft":
            info.mc_version = ver
        elif "fabric-loader" in uid:
            info.loader_kind, info.loader_version = "fabric", ver
        elif "quilt-loader" in uid:
            info.loader_kind, info.loader_version = "quilt", ver
        elif "neoforge" in uid:
            info.loader_kind, info.loader_version = "neoforge", ver
        elif "forge" in uid:
            info.loader_kind, info.loader_version = "forge", ver
    if not info.mc_version:
        raise PackFormatError("MultiMC 整合包没有写 Minecraft 版本")
    return info


def _parse_curseforge(path: Path, data: dict, names: list[str]) -> PackInfo:
    mc = data.get("minecraft") or {}
    info = PackInfo(kind="curseforge", name=str(data.get("name") or path.stem),
                    mc_version=str(mc.get("version") or ""))
    for item in mc.get("modLoaders") or []:
        if not isinstance(item, dict):
            continue
        raw = str(item.get("id") or "")
        if not raw:
            continue
        if raw.startswith("forge-"):
            info.loader_kind, info.loader_version = "forge", raw[len("forge-"):]
        elif raw.startswith("fabric-"):
            info.loader_kind, info.loader_version = "fabric", raw[len("fabric-"):]
        elif raw.startswith("neoforge-"):
            info.loader_kind, info.loader_version = "neoforge", raw[len("neoforge-"):]
        elif raw.startswith("quilt-"):
            info.loader_kind, info.loader_version = "quilt", raw[len("quilt-"):]
        break
    if not info.mc_version:
        raise PackFormatError("CurseForge 整合包没有写 Minecraft 版本")
    cf_files = [f for f in (data.get("files") or [])
                if isinstance(f, dict) and f.get("projectID") and f.get("fileID")]
    info.cf_files = cf_files
    info.notes.append(f"清单里列了 {len(cf_files)} 个文件")
    return info


# ---------------------------------------------------------------- 安装


def _ensure_vanilla(game_dir: Path, mc: str, on_log, progress_cb, threads: int) -> None:
    if mc in set(list_installed_versions(game_dir)):
        on_log(f"原版 {mc} 已存在")
        return
    url = modpack._manifest_url(mc)
    if not url:
        raise PackFormatError(f"版本清单里找不到 {mc}")
    on_log(f"缺少原版 {mc}，先安装…")
    inst = Installer(game_dir, source="official", threads=threads, log=on_log)
    ok, msg = inst.install(mc, url, progress_cb=progress_cb)
    if not ok:
        raise PackFormatError(f"原版 {mc} 安装失败：{msg}")


def _ensure_loader(game_dir: Path, info: PackInfo, on_log, progress_cb,
                   cancel) -> str:
    if not (info.loader_kind and info.loader_version):
        return info.mc_version
    for vid in loaders.installed_loader_versions(game_dir):
        if info.loader_version in vid and info.mc_version in vid:
            if loaders.loader_complete(game_dir, vid):
                on_log(f"加载器已存在：{vid}")
                return vid
            # 上次装到一半就断了：版本文件建了但库文件缺，直接重装覆盖
            on_log(f"加载器 {vid} 不完整，重新安装")
    from .java import detect_all
    from .javaauto import find_or_install
    from .launcher import version_meta
    need = 17
    try:
        need = int((version_meta(game_dir, info.mc_version).get("javaVersion") or 17))
    except Exception:                                     # noqa: BLE001
        pass
    java = find_or_install(game_dir, need, detect_all(game_dir),
                           on_log=on_log, progress_cb=progress_cb)
    on_log(f"安装加载器 {info.loader_kind} {info.loader_version} …")
    return loaders.install(info.loader_kind, info.mc_version, info.loader_version,
                           game_dir, java, on_log=on_log, cancel=cancel)


def _extract_into(zf: zipfile.ZipFile, names: list[str], prefix: str,
                  dest_root: Path, on_log, cancel) -> int:
    count = 0
    for name in names:
        rel = name
        if prefix:
            if not name.lower().startswith(prefix.lower()):
                continue
            rel = name[len(prefix):]
        if not rel or rel.endswith("/"):
            continue
        if cancel and cancel():
            raise PackFormatError("用户取消")
        target = dest_root / rel
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(name) as src, open(target, "wb") as out:
                out.write(src.read())
            count += 1
        except OSError:
            continue
    if count:
        on_log(f"解出 {count} 个文件")
    return count


def _install_cf_mods(info: PackInfo, version_dir: Path, on_log, progress_cb,
                     cancel) -> None:
    """CurseForge 包里的模组：按 projectID + fileID 拼 CDN 直链自动下载。"""
    if not info.cf_files:
        on_log("清单里没有模组条目，跳过模组下载")
        return
    mods_dir = version_dir / "mods"
    try:
        ok, missing = curseforge.install(info.cf_files, mods_dir, on_log=on_log,
                                         progress_cb=progress_cb, cancel=cancel)
    except Exception as exc:                            # noqa: BLE001
        on_log(f"CurseForge 模组下载失败：{exc}")
        on_log("配置已铺好，可在 Mod 页手动补装模组")
        return
    on_log(curseforge.summary(ok, missing))
    if missing:
        on_log(curseforge.describe_missing(missing))


def install_any(path: Path, game_dir: Path, base_version: str = "",
                on_log: Callable[[str], None] = lambda _m: None,
                progress_cb: Callable | None = None,
                cancel: Callable[[], bool] | None = None,
                threads: int = 16) -> str:
    """识别格式并安装，返回新的版本 id。"""
    path = Path(path)
    game_dir = Path(game_dir)
    info = detect(path)
    on_log(f"识别为{info.label}：{info.name}")

    if info.kind == "mrpack":
        return modpack.install(path, game_dir, on_log=on_log,
                               progress_cb=progress_cb, cancel=cancel, threads=threads)

    if info.kind == "mod":
        raise PackFormatError("这是单个 Mod 文件，不是整合包；请拖到 Mod 页或使用「导入本地 Mod」")

    if not info.mc_version:
        if not base_version:
            raise PackFormatError("这个压缩包没写 Minecraft 版本，请先在版本列表里选中一个版本再导入")
        info.mc_version = base_version
        on_log(f"包内未声明版本，继承当前选中的 {base_version}")

    _ensure_vanilla(game_dir, info.mc_version, on_log, progress_cb, threads)
    parent = _ensure_loader(game_dir, info, on_log, progress_cb, cancel)

    pack_id = modpack.safe_name(info.name or path.stem)
    version_dir = game_dir / "versions" / pack_id
    modpack._write_version_json(version_dir, pack_id, parent)
    on_log(f"创建实例版本：{pack_id}（继承 {parent}）")

    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        if info.kind == "multimc":
            from . import instances

            instances.ensure_instance(version_dir)
            prefixes = [p for p in (".minecraft/", "minecraft/") if any(
                n.lower().startswith(p) for n in names)]
            prefix = prefixes[0] if prefixes else ""
            _extract_into(zf, names, prefix, version_dir, on_log, cancel)
        elif info.kind == "curseforge":
            prefixes = [p for p in ("overrides/",) if any(
                n.lower().startswith(p) for n in names)]
            _extract_into(zf, names, prefixes[0] if prefixes else "", version_dir,
                          on_log, cancel)
            _install_cf_mods(info, version_dir, on_log, progress_cb, cancel)
        else:
            _extract_into(zf, names, "", version_dir, on_log, cancel)

        if info.kind == "mrpack":                          # 理论上不会到这里
            modpack._extract_overrides(path, version_dir, on_log, cancel)

    on_log(f"整合包导入完成：{pack_id}")
    return pack_id
