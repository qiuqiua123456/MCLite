"""版本元数据：规则匹配、库与资源文件解析、启动参数模板。

兼容两代格式：
    * 1.13+  arguments.game / arguments.jvm
    * 1.12-  minecraftArguments 字符串
"""

from __future__ import annotations

import json
import platform
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .downloader import DownloadTask

VERSION_MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"

# ---------------------------------------------------------------- 系统信息

def os_name() -> str:
    if platform.system() == "Windows":
        return "windows"
    if platform.system() == "Darwin":
        return "osx"
    return "linux"


def os_arch() -> str:
    machine = platform.machine().lower()
    if machine in ("amd64", "x86_64", "x64"):
        return "x86_64"
    if machine in ("i386", "i686", "x86"):
        return "x86"
    if machine in ("arm64", "aarch64"):
        return "arm64"
    return machine or "x86_64"


_OS_VERSION = platform.version()


# ---------------------------------------------------------------- 规则匹配

def _match_rule_os(rule_os: dict[str, Any]) -> bool:
    name = rule_os.get("name")
    if name and name != os_name():
        return False
    arch = rule_os.get("arch")
    if arch and arch != os_arch():
        return False
    ver = rule_os.get("version")
    if ver:
        try:
            if not re.search(ver, _OS_VERSION):
                return False
        except re.error:
            pass
    return True


def rules_allow(rules: list[dict[str, Any]] | None, features: dict[str, bool] | None = None) -> bool:
    """Minecraft 规则求值：无 rules 视为允许；有 rules 时默认拒绝，按顺序取最后命中的动作。"""
    if not rules:
        return True
    features = features or {}
    allowed = False
    for rule in rules:
        action = rule.get("action", "allow")
        rule_os = rule.get("os")
        rule_feat = rule.get("features")
        if rule_os and not _match_rule_os(rule_os):
            continue
        if rule_feat:
            if any(features.get(k) != v for k, v in rule_feat.items()):
                continue
        allowed = action == "allow"
    return allowed


# ---------------------------------------------------------------- 库解析

@dataclass
class ResolvedLibrary:
    name: str
    path: str                     # 相对 libraries/ 的路径
    url: str | None = None
    sha1: str | None = None
    size: int | None = None
    is_native: bool = False
    extract_exclude: list[str] | None = None


def maven_to_path(name: str) -> str:
    """group:artifact:version[:classifier] -> group/artifact/version/artifact-version[-classifier].jar"""
    parts = name.split(":")
    if len(parts) < 3:
        raise ValueError(f"非法 Maven 坐标：{name}")
    group, artifact, version = parts[0], parts[1], parts[2]
    classifier = parts[3] if len(parts) > 3 else None
    filename = f"{artifact}-{version}"
    if classifier:
        filename += f"-{classifier}"
    filename += ".jar"
    return "/".join(group.split(".") + [artifact, version, filename])


def lib_filename(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1]


def resolve_libraries(version_json: dict[str, Any]) -> list[ResolvedLibrary]:
    """返回需要落盘的库（含 natives），已按当前系统过滤。"""
    out: list[ResolvedLibrary] = []
    seen: set[str] = set()

    for lib in version_json.get("libraries", []):
        if not rules_allow(lib.get("rules")):
            continue
        downloads = lib.get("downloads") or {}
        name = lib.get("name", "")

        # 现代格式：artifact 直接给 path/url；natives 也走 artifact（自带 rules）
        artifact = downloads.get("artifact")
        if artifact:
            path = artifact.get("path") or maven_to_path(name)
            if path in seen:
                continue
            seen.add(path)
            out.append(ResolvedLibrary(
                name=name,
                path=path,
                url=artifact.get("url"),
                sha1=artifact.get("sha1"),
                size=artifact.get("size"),
                is_native="natives-" in path or "natives-" in name,
                extract_exclude=(lib.get("extract") or {}).get("exclude"),
            ))
            continue

        # 老格式：natives + classifiers
        natives = lib.get("natives") or {}
        classifier_key = natives.get(os_name())
        classifiers = downloads.get("classifiers") or {}
        if classifier_key and classifier_key in classifiers:
            entry = classifiers[classifier_key]
            path = entry.get("path") or _native_path(name, os_name())
            if path in seen:
                continue
            seen.add(path)
            out.append(ResolvedLibrary(
                name=name,
                path=path,
                url=entry.get("url"),
                sha1=entry.get("sha1"),
                size=entry.get("size"),
                is_native=True,
                extract_exclude=(lib.get("extract") or {}).get("exclude"),
            ))
            continue

        # 既无 artifact 也无 natives：用 Maven 坐标拼 URL（部分 Forge 库这样）
        if name and not downloads:
            try:
                path = maven_to_path(name)
            except ValueError:
                continue
            if path in seen:
                continue
            seen.add(path)
            out.append(ResolvedLibrary(name=name, path=path, url=None))

    return out


def _native_path(name: str, osname: str) -> str:
    parts = name.split(":")
    group, artifact, version = parts[0], parts[1], parts[2]
    filename = f"{artifact}-{version}-natives-{osname}.jar"
    return "/".join(group.split(".") + [artifact, version, filename])


# ---------------------------------------------------------------- 资源文件

ASSETS_URL = "https://resources.download.minecraft.net"


@dataclass
class AssetIndex:
    id: str
    url: str | None = None
    sha1: str | None = None
    size: int | None = None
    total_size: int = 0


def asset_index_of(version_json: dict[str, Any]) -> AssetIndex | None:
    idx = version_json.get("assetIndex")
    if not idx:
        return None
    return AssetIndex(
        id=idx.get("id") or version_json.get("assets") or "legacy",
        url=idx.get("url"),
        sha1=idx.get("sha1"),
        size=idx.get("size"),
        total_size=idx.get("totalSize") or 0,
    )


def asset_objects(index_json: dict[str, Any]) -> Iterable[tuple[str, str, int]]:
    """产 (hash, 相对路径, 大小)。"""
    for name, obj in (index_json.get("objects") or {}).items():
        h = obj.get("hash")
        if not h:
            continue
        yield h, f"{h[:2]}/{h}", int(obj.get("size") or 0)


def build_asset_tasks(index_json: dict[str, Any], assets_dir: Path) -> list[DownloadTask]:
    tasks: list[DownloadTask] = []
    seen: set[str] = set()
    for h, rel, size in asset_objects(index_json):
        if rel in seen:
            continue
        seen.add(rel)
        tasks.append(DownloadTask(
            url=f"{ASSETS_URL}/{rel}",
            dest=assets_dir / "objects" / rel,
            sha1=h,
            size=size,
        ))
    return tasks


# ---------------------------------------------------------------- 版本清单

@dataclass
class VersionSummary:
    id: str
    type: str
    url: str
    release_time: str = ""
    raw: dict[str, Any] | None = None


def parse_manifest(manifest: dict[str, Any]) -> list[VersionSummary]:
    out = []
    for v in manifest.get("versions", []):
        out.append(VersionSummary(
            id=v.get("id", ""),
            type=v.get("type", "release"),
            url=v.get("url", ""),
            release_time=v.get("releaseTime", ""),
            raw=v,
        ))
    return out


# ---------------------------------------------------------------- 参数模板

def collect_arguments(version_json: dict[str, Any], key: str) -> list[str]:
    """从 arguments.<key> 里取出当前系统适用的字符串参数。"""
    args = (version_json.get("arguments") or {}).get(key) or []
    result: list[str] = []
    for item in args:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            if rules_allow(item.get("rules")):
                value = item.get("value")
                if isinstance(value, str):
                    result.append(value)
                elif isinstance(value, list):
                    result.extend(str(x) for x in value)
    return result


def game_arguments(version_json: dict[str, Any]) -> list[str]:
    """统一返回参数列表；老格式按空格切分。"""
    if "arguments" in version_json and isinstance(version_json["arguments"], dict):
        return collect_arguments(version_json, "game")
    legacy = version_json.get("minecraftArguments") or ""
    return legacy.split() if legacy else []


def jvm_arguments(version_json: dict[str, Any]) -> list[str]:
    if "arguments" in version_json and isinstance(version_json["arguments"], dict):
        return collect_arguments(version_json, "jvm")
    return ["-Djava.library.path=${natives_directory}", "-cp", "${classpath}"]


_PLACEHOLDER = re.compile(r"\$\{([^}]+)\}")


def substitute(arg: str, values: dict[str, Any]) -> str:
    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        v = values.get(key)
        return "" if v is None else str(v)
    return _PLACEHOLDER.sub(repl, arg)


# ---------------------------------------------------------------- 版本 JSON

def read_version_json(version_dir: Path, version_id: str) -> dict[str, Any] | None:
    for name in (f"{version_id}.json",):
        p = version_dir / name
        if p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as fh:
                    return json.load(fh)
            except (OSError, ValueError):
                return None
    return None


def read_client_json(version_dir: Path) -> dict[str, Any] | None:
    """不依赖版本 id，取目录里第一个 json。"""
    try:
        for p in sorted(version_dir.glob("*.json")):
            with open(p, "r", encoding="utf-8") as fh:
                return json.load(fh)
    except (OSError, ValueError):
        return None
    return None


def jar_path_of(version_dir: Path, version_json: dict[str, Any]) -> Path | None:
    jar = version_dir / f"{version_json.get('id', '')}.jar"
    if jar.is_file():
        return jar
    try:
        for p in sorted(version_dir.glob("*.jar")):
            return p
    except OSError:
        return None
    return None
