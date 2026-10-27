"""Java 运行时自动下载。

Mojang 把各版本 OpenJDK 作为「java runtime」发布在
``launchermeta.mojang.com/v1/products/java-runtime/...`` 的清单里，
每份清单又是一堆散文件的下载地址。这里负责选组件、下文件、定位 java.exe。

下载到 ``<游戏目录>/runtime/<组件名>/<版本名>/``，和官方启动器的布局一致。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

from .downloader import DownloadTask, Downloader, fetch_json
from .java import JavaInfo, _run_java

RUNTIME_MANIFEST = (
    "https://launchermeta.mojang.com/v1/products/java-runtime/"
    "2ec0cc96c44e5a76b9c8b7c39df7210883d12871/all.json"
)

#: 常见组件 → 对应的大版本号（仅用于在清单缺失时兜底）
COMPONENTS: list[tuple[str, int]] = [
    ("jre-legacy", 8),
    ("java-runtime-alpha", 16),
    ("java-runtime-beta", 17),
    ("java-runtime-gamma", 17),
    ("java-runtime-delta", 21),
    ("java-runtime-epsilon", 25),
]

PLATFORM_KEYS = ("windows-x64", "windows-x86", "windows-arm64")


class JavaDownloadError(Exception):
    pass


def _major_of(name: str) -> int:
    """从 ``17.0.8`` / ``1.8.0_74`` / ``8u51-cacert462b08`` 这类版本名里取出主版本号。"""
    text = str(name or "").strip()
    match = re.match(r"^(\d+)(?:u(\d+))?", text)
    if not match:
        return 0
    first = int(match.group(1))
    if match.group(2):                      # 8u51 → 8
        return first
    if first == 1:                          # 1.8.0_74 → 8
        second = re.match(r"^1\.(\d+)", text)
        if second:
            return int(second.group(1))
        return 1
    return first


def runtime_root(game_dir: Path) -> Path:
    return Path(game_dir) / "runtime"


def installed_runtimes(game_dir: Path) -> list[tuple[Path, str]]:
    """列出已下载的运行时 ``[(java.exe 路径, "组件 版本")]``。"""
    root = runtime_root(game_dir)
    found: list[tuple[Path, str]] = []
    if not root.is_dir():
        return found
    try:
        for comp in root.iterdir():
            if not comp.is_dir():
                continue
            for ver in comp.iterdir():
                if not ver.is_dir():
                    continue
                for exe in ("bin/javaw.exe", "bin/java.exe"):
                    p = ver / exe
                    if p.is_file():
                        found.append((p.resolve(), f"{comp.name} {ver.name}"))
                        break
    except OSError:
        pass
    return found


def pick_component(manifest: dict, required_major: int) -> tuple[str, dict]:
    """从清单里挑一个满足要求的组件，返回 ``(组件名, 该组件的首个条目)``。"""
    for key in PLATFORM_KEYS:
        table = manifest.get(key)
        if not isinstance(table, dict) or not table:
            continue
        best: tuple[int, str, dict] | None = None
        for name, entries in table.items():
            if not isinstance(entries, list) or not entries:
                continue
            if "snapshot" in name:          # 预发布组件不要
                continue
            entry = entries[0]
            version_name = str((entry.get("version") or {}).get("name") or "")
            major = _major_of(version_name)
            if major < required_major:
                continue
            if best is None or major < best[0]:
                best = (major, name, entry)
        if best:
            return best[1], best[2]
        # 没有满足的，退而求其次拿最高的
        fallback: tuple[int, str, dict] | None = None
        for name, entries in table.items():
            if not isinstance(entries, list) or not entries or "snapshot" in name:
                continue
            major = _major_of((entries[0].get("version") or {}).get("name") or "")
            if fallback is None or major > fallback[0]:
                fallback = (major, name, entries[0])
        if fallback:
            return fallback[1], fallback[2]
    raise JavaDownloadError("清单里没有适用于本机平台的 Java 运行时")


def install_java(
    game_dir: Path,
    required_major: int,
    on_log: Callable[[str], None] = lambda _m: None,
    progress_cb: Callable | None = None,
    threads: int = 8,
) -> JavaInfo:
    """下载并安装一个满足 ``required_major`` 的 Java，返回可用的 JavaInfo。"""
    on_log(f"查询 Java {required_major} 运行时清单…")
    try:
        manifest = fetch_json(RUNTIME_MANIFEST, timeout=30)
    except Exception as exc:                            # noqa: BLE001
        raise JavaDownloadError(f"拿不到 Java 运行时清单：{exc}") from exc
    if not isinstance(manifest, dict):
        raise JavaDownloadError("Java 运行时清单格式异常")

    component, entry = pick_component(manifest, required_major)
    version_name = str((entry.get("version") or {}).get("name") or "unknown")
    url = str((entry.get("manifest") or {}).get("url") or "")
    if not url:
        raise JavaDownloadError(f"组件 {component} 缺少清单地址")
    on_log(f"选择 {component}（{version_name}），适合 Java {required_major}+")

    try:
        detail = fetch_json(url, timeout=30)
    except Exception as exc:                            # noqa: BLE001
        raise JavaDownloadError(f"下载组件清单失败：{exc}") from exc

    files = (detail or {}).get("files") or {}
    if not isinstance(files, dict) or not files:
        raise JavaDownloadError("组件清单里没有文件列表")

    target = runtime_root(game_dir) / component / version_name
    tasks: list[DownloadTask] = []
    for rel, info in files.items():
        if not isinstance(info, dict):
            continue
        kind = info.get("type")
        dest = target / rel
        if kind == "directory":
            try:
                dest.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
            continue
        if kind != "file":
            continue
        raw = (info.get("downloads") or {}).get("raw") or {}
        file_url = str(raw.get("url") or "")
        if not file_url:
            continue
        tasks.append(DownloadTask(
            url=file_url,
            dest=dest,
            sha1=raw.get("sha1") or None,
            size=raw.get("size") or None,
        ))

    if not tasks:
        raise JavaDownloadError("组件清单里没有可下载的文件")

    on_log(f"开始下载 {component} {version_name}（{len(tasks)} 个文件）…")
    dl = Downloader(threads=max(2, threads))
    ok, bad = dl.run(tasks, source="official", progress_cb=progress_cb, on_log=on_log)
    if bad:
        on_log(f"有 {bad} 个文件下载失败")

    exe = None
    for candidate in ("bin/javaw.exe", "bin/java.exe"):
        p = target / candidate
        if p.is_file():
            exe = p
            break
    if exe is None:
        raise JavaDownloadError(f"下载完成但没找到 java.exe（{target}）")

    info = _run_java(exe)
    if info is None:
        raise JavaDownloadError("下载的 Java 无法运行")
    on_log(f"Java {info.version} 就绪：{exe}")
    return info


def find_or_install(
    game_dir: Path,
    required_major: int,
    javas: list[JavaInfo],
    on_log: Callable[[str], None] = lambda _m: None,
    progress_cb: Callable | None = None,
) -> JavaInfo:
    """先看已下载的运行时，再看已检测到的，最后才下载。"""
    for path, label in installed_runtimes(game_dir):
        info = _run_java(path)
        if info and info.major >= required_major:
            on_log(f"使用已下载的运行时：{label}（Java {info.version}）")
            return info
    for j in javas:
        if j.major >= required_major:
            return j
    return install_java(game_dir, required_major, on_log=on_log, progress_cb=progress_cb)


def manifest_summary(manifest: dict) -> str:
    """调试用：把清单压成一行摘要。"""
    parts = []
    for key in PLATFORM_KEYS:
        table = manifest.get(key)
        if isinstance(table, dict):
            parts.append(f"{key}: {len(table)} 个组件")
    return json.dumps(parts, ensure_ascii=False)
