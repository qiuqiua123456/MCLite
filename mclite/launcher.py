"""启动器核心：组装 classpath、解压 natives、拼装命令行并拉起进程。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import APP_NAME, __version__
from .java import JavaInfo
from .versionmeta import (
    game_arguments,
    jar_path_of,
    jvm_arguments,
    read_client_json,
    read_version_json,
    resolve_libraries,
    substitute,
)

_CREATE_NEW_CONSOLE = 0x00000010 if sys.platform == "win32" else 0
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def offline_uuid(name: str) -> str:
    """离线模式 UUID：Java 的 nameUUIDFromBytes("OfflinePlayer:" + name)。"""
    import hashlib
    digest = bytearray(hashlib.md5(("OfflinePlayer:" + name).encode("utf-8")).digest())
    digest[6] = (digest[6] & 0x0F) | 0x30          # version 3
    digest[8] = (digest[8] & 0x3F) | 0x80          # variant
    h = digest.hex()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


@dataclass
class LaunchOptions:
    version_id: str
    player_name: str = "Steve"
    uuid: str = ""
    access_token: str = "0"
    user_type: str = "legacy"
    memory_mb: int = 4096
    jvm_args: str = ""
    extra_args: str = ""
    width: int = 900
    height: int = 560
    fullscreen: bool = False
    demo: bool = False
    #: 隔离实例的游戏目录（None 表示与游戏目录共用）
    instance_dir: Path | None = None
    #: 需要以 -javaagent: 形式挂载的代理（如 authlib-injector）
    javaagents: list[str] = field(default_factory=list)

    @property
    def work_dir(self) -> Path | None:
        return self.instance_dir


@dataclass
class LaunchResult:
    ok: bool
    command: list[str] = field(default_factory=list)
    error: str = ""
    process: subprocess.Popen | None = None
    log_path: Path | None = None


class LaunchError(Exception):
    pass


class GameLauncher:
    def __init__(self, game_dir: Path) -> None:
        self.game_dir = Path(game_dir)
        self.versions_dir = self.game_dir / "versions"
        self.libraries_dir = self.game_dir / "libraries"
        self.assets_dir = self.game_dir / "assets"
        self._log_handles: list[Any] = []

    # ------------------------------------------------------------ 读取

    def load_version(self, version_id: str) -> dict[str, Any]:
        """读取版本 JSON，并按 ``inheritsFrom`` 逐层合并父版本。"""
        data = self._read_raw(version_id)
        return self._resolve_inherits(version_id, data, set())

    def _read_raw(self, version_id: str) -> dict[str, Any]:
        vdir = self.versions_dir / version_id
        if not vdir.is_dir():
            raise LaunchError(f"版本目录不存在：{vdir}")
        data = read_version_json(vdir, version_id) or read_client_json(vdir)
        if not data:
            raise LaunchError(f"版本 JSON 缺失：{vdir}")
        return data

    def _resolve_inherits(self, version_id: str, data: dict[str, Any],
                          seen: set[str]) -> dict[str, Any]:
        parent_id = data.get("inheritsFrom")
        if not parent_id:
            data.setdefault("id", version_id)
            return data
        if parent_id in seen or parent_id == version_id:
            raise LaunchError(f"版本继承出现循环：{version_id} → {parent_id}")
        seen.add(version_id)
        try:
            parent_raw = self._read_raw(parent_id)
        except LaunchError as exc:
            raise LaunchError(f"{version_id} 依赖的父版本不可用：{exc}") from exc
        parent = self._resolve_inherits(parent_id, parent_raw, seen)
        merged = self._merge(parent, data)
        merged["id"] = version_id
        # 客户端 jar 通常来自父版本（Forge / Fabric / Quilt 只放补丁），记下来给
        # version_jar 用。必须一路追到最顶层：整合包的链是
        # 「整合包 → quilt-loader-xxx → 1.20.1」，jar 在 1.20.1 目录里，
        # 只记 parent["id"] 会指向 quilt-loader 那个没有 jar 的目录。
        merged["_jar_from"] = (data.get("jar") or parent.get("_jar_from")
                               or parent.get("id") or parent_id)
        return merged

    @staticmethod
    def _lib_key(lib: dict[str, Any]) -> str:
        name = str(lib.get("name") or "")
        parts = name.split(":")
        if len(parts) >= 3:
            key = ":".join(parts[:2])
            if len(parts) >= 4:
                key += ":" + parts[3]
            return key
        return name

    @classmethod
    def _merge(cls, parent: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
        """按官方规则合并：子版本覆盖同名字段，libraries / arguments 累加。"""
        out = dict(parent)
        for key, value in child.items():
            if key in ("libraries", "arguments", "minecraftArguments", "inheritsFrom", "id"):
                continue
            out[key] = value

        # libraries：同 group:artifact[:classifier] 以子版本为准，其余按父→子顺序保留
        merged: list[dict[str, Any]] = []
        index: dict[str, int] = {}
        for lib in list(parent.get("libraries") or []) + list(child.get("libraries") or []):
            if not isinstance(lib, dict):
                continue
            key = cls._lib_key(lib)
            if key in index:
                merged[index[key]] = lib
            else:
                index[key] = len(merged)
                merged.append(lib)
        out["libraries"] = merged

        # arguments / minecraftArguments
        if "arguments" in parent or "arguments" in child:
            pargs = parent.get("arguments") or {}
            cargs = child.get("arguments") or {}
            arg: dict[str, Any] = {}
            for slot in ("game", "jvm"):
                arg[slot] = list(pargs.get(slot) or []) + list(cargs.get(slot) or [])
            for slot, value in cargs.items():
                if slot in ("game", "jvm"):
                    continue
                arg[slot] = value
            out["arguments"] = arg
        if child.get("minecraftArguments"):
            base = str(parent.get("minecraftArguments") or "").strip()
            out["minecraftArguments"] = (base + " " + str(child["minecraftArguments"]).strip()).strip()
        return out

    def version_jar(self, version_id: str, vjson: dict[str, Any]) -> Path:
        vdir = self.versions_dir / version_id
        jar = jar_path_of(vdir, vjson)
        if jar:
            return jar
        # 继承了父版本（Forge/Fabric/NeoForge）时，客户端 jar 在父版本目录里
        src = vjson.get("_jar_from") or vjson.get("jar")
        if src:
            jdir = self.versions_dir / str(src)
            if jdir.is_dir():
                jar = jar_path_of(jdir, {"id": str(src)})
                if jar:
                    return jar
        raise LaunchError(f"客户端 jar 缺失（{vdir}）")

    def asset_index_name(self, vjson: dict[str, Any]) -> str:
        idx = vjson.get("assetIndex") or {}
        return idx.get("id") or vjson.get("assets") or "legacy"

    def assets_available(self, vjson: dict[str, Any]) -> bool:
        name = self.asset_index_name(vjson)
        return (self.assets_dir / "indexes" / f"{name}.json").is_file()

    # ------------------------------------------------------------ 构建命令

    def build_command(
        self,
        version_id: str,
        java: JavaInfo,
        opts: LaunchOptions,
    ) -> list[str]:
        vjson = self.load_version(version_id)
        vdir = self.versions_dir / version_id
        jar = self.version_jar(version_id, vjson)

        # natives 解压
        natives_dir = vdir / f"{version_id}-natives"
        self._extract_natives(vjson, natives_dir)

        # classpath
        cp_entries: list[str] = []
        missing: list[str] = []
        for lib in resolve_libraries(vjson):
            p = self.libraries_dir / Path(lib.path)
            if p.is_file():
                cp_entries.append(str(p))
            elif not lib.is_native:
                missing.append(lib.path)
        cp_entries.append(str(jar))
        if missing:
            # 缺库不阻断启动，交给游戏自己报错，但记在错误里
            pass
        # Forge / NeoForge 用 BootstrapLauncher，它们自己维护模块层：
        # 原版 jar 再上 classpath 会多出一个 "1.20.1" 自动模块，和 Forge 的
        # "minecraft" 模块抢同一个包（net.minecraft.server 等）导致启动即崩。
        main_class = str(vjson.get("mainClass") or "").lower()
        bootstrap = "bootstraplauncher" in main_class
        has_client_lib = any(
            str(lib.get("name") or "").startswith("net.minecraft:client:")
            for lib in (vjson.get("libraries") or [])
        )
        if bootstrap or has_client_lib:
            cp_entries = [p for p in cp_entries if p != str(jar)]
        classpath = os.pathsep.join(cp_entries)

        uuid_str = opts.uuid or offline_uuid(opts.player_name)
        token = opts.access_token or "0"
        asset_index = self.asset_index_name(vjson)

        values = {
            "auth_player_name": opts.player_name,
            "version_name": version_id,
            "game_directory": str(opts.instance_dir or self.game_dir),
            "assets_root": str(self.assets_dir),
            "game_assets": str(self.assets_dir / "virtual" / "legacy"),
            "assets_index_name": asset_index,
            "auth_uuid": uuid_str.replace("-", ""),
            "auth_access_token": token,
            "auth_session": f"token:{token}:{uuid_str.replace('-', '')}",
            "auth_xuid": "0",
            "user_type": opts.user_type,
            "version_type": vjson.get("type", "release"),
            "classpath": classpath,
            "library_directory": str(self.libraries_dir),
            "classpath_separator": os.pathsep,
            "natives_directory": str(natives_dir),
            "launcher_name": APP_NAME,
            "launcher_version": __version__,
            "clientid": "0",
            "resolution_width": str(opts.width),
            "resolution_height": str(opts.height),
            "user_properties": "{}",
            "profile_name": APP_NAME,
        }

        cmd: list[str] = [str(java.path)]

        # JVM 参数
        raw_jvm = jvm_arguments(vjson)
        rendered_jvm: list[str] = []
        for a in raw_jvm:
            ra = substitute(a, values)
            # 去掉启动器自己会加的参数，避免重复
            if ra.startswith("-Xmx") or ra.startswith("-Xms"):
                continue
            if ra.startswith("-Dminecraft.launcher"):
                continue
            rendered_jvm.append(ra)

        cmd.append(f"-Xms{max(512, opts.memory_mb // 4)}M")
        cmd.append(f"-Xmx{opts.memory_mb}M")
        cmd.append("-Dfile.encoding=UTF-8")
        cmd.append(f"-Dminecraft.launcher.brand={APP_NAME}")
        cmd.append(f"-Dminecraft.launcher.version={__version__}")
        cmd.extend(rendered_jvm)

        if opts.jvm_args.strip():
            cmd.extend(a for a in opts.jvm_args.split() if a)

        # -javaagent（第三方皮肤站认证需要 authlib-injector）
        for agent in opts.javaagents:
            if agent:
                cmd.append(agent if agent.startswith("-javaagent:") else f"-javaagent:{agent}")

        # 主类
        main_class = vjson.get("mainClass")
        if not main_class:
            raise LaunchError("版本 JSON 里没有 mainClass（可能是不完整的继承版本）")
        cmd.append(main_class)

        # 游戏参数
        gargs = game_arguments(vjson)
        if not gargs:
            raise LaunchError("版本 JSON 里没有游戏参数")
        skip_next = False
        for a in gargs:
            if skip_next:
                skip_next = False
                continue
            if a in ("--width", "--height"):
                skip_next = True
                continue
            ra = substitute(a, values)
            cmd.append(ra)
        cmd.append("--width")
        cmd.append(str(opts.width))
        cmd.append("--height")
        cmd.append(str(opts.height))
        if opts.fullscreen:
            cmd.append("--fullscreen")
        if opts.demo:
            cmd.append("--demo")

        if opts.extra_args.strip():
            cmd.extend(a for a in opts.extra_args.split() if a)

        return cmd

    # ------------------------------------------------------------ natives

    def _extract_natives(self, vjson: dict[str, Any], natives_dir: Path) -> None:
        natives_dir.mkdir(parents=True, exist_ok=True)
        for lib in resolve_libraries(vjson):
            if not lib.is_native:
                continue
            jar = self.libraries_dir / Path(lib.path)
            if not jar.is_file():
                continue
            exclude = lib.extract_exclude or ["META-INF/"]
            try:
                with zipfile.ZipFile(jar) as zf:
                    for info in zf.infolist():
                        if info.is_dir():
                            continue
                        name = info.filename
                        if any(name.startswith(p) for p in exclude):
                            continue
                        target = natives_dir / name
                        if target.is_file() and target.stat().st_size == info.file_size:
                            continue
                        try:
                            target.parent.mkdir(parents=True, exist_ok=True)
                            with zf.open(info) as src, open(target, "wb") as dst:
                                shutil.copyfileobj(src, dst)
                        except OSError:
                            continue
            except (OSError, zipfile.BadZipFile):
                continue

    # ------------------------------------------------------------ 启动

    def launch(
        self,
        version_id: str,
        java: JavaInfo,
        opts: LaunchOptions,
        cwd: Path | None = None,
        log_file: Path | None = None,
        show_console: bool = False,
    ) -> LaunchResult:
        try:
            cmd = self.build_command(version_id, java, opts)
        except LaunchError as exc:
            return LaunchResult(ok=False, error=str(exc))
        except Exception as exc:                        # noqa: BLE001
            return LaunchResult(ok=False, error=f"{type(exc).__name__}: {exc}")

        workdir = cwd or opts.instance_dir or self.game_dir
        workdir.mkdir(parents=True, exist_ok=True)

        # 游戏输出重定向到日志文件，界面可以实时读取
        log_path = log_file or (workdir / "logs" / f"mclite-{version_id}-latest.log")
        stdout: Any = subprocess.DEVNULL
        stderr: Any = subprocess.DEVNULL
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            handle = open(log_path, "wb")
            self._log_handles.append(handle)
            stdout = handle
            stderr = subprocess.STDOUT
        except OSError:
            log_path = None

        flags = 0
        if not show_console:
            flags |= _CREATE_NO_WINDOW

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(workdir),
                stdout=stdout,
                stderr=stderr,
                stdin=subprocess.DEVNULL,
                creationflags=flags,
            )
        except OSError as exc:
            return LaunchResult(ok=False, command=cmd, error=f"启动失败：{exc}")
        return LaunchResult(ok=True, command=cmd, process=proc, log_path=log_path)


# ---------------------------------------------------------------- 实例扫描

def _read_raw_json(vdir: Path, version_id: str) -> dict[str, Any] | None:
    """读版本目录里的原始 JSON，读不到/写坏了都返回 None。

    半装残留经常只剩一个写了一半的 JSON（安装中途被杀），``json.load`` 会抛
    ``ValueError``，这种目录必须当成「没装」而不是「已装」。
    """
    for name in (f"{version_id}.json", f"{vdir.name}.json"):
        p = vdir / name
        if not p.is_file():
            continue
        try:
            with open(p, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None
    try:
        for p in sorted(vdir.glob("*.json")):
            try:
                with open(p, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, ValueError):
                continue
            if isinstance(data, dict):
                return data
    except OSError:
        pass
    return None


def _has_jar(vdir: Path) -> bool:
    try:
        for p in vdir.glob("*.jar"):
            if p.is_file() and p.stat().st_size > 0:
                return True
    except OSError:
        pass
    return False


def version_complete(game_dir: Path, version_id: str) -> bool:
    """这个版本目录算不算「真的装好了」。

    三种情况判为未装完，不进列表（用户反馈「我明明还没安装这几个哪来的」）：

    1. 目录里没有可解析的版本 JSON（安装写了一半就中断）；
    2. 自己有 jar 但 jar 是 0 字节（下载失败留下的空壳）；
    3. 既没有自己的 jar，也追溯不到带 jar 的父版本 —— Fabric/Quilt 的
       profile 只有 JSON，jar 在原版目录里，所以必须一路往上找，不能只看本层。
    """
    vdir = Path(game_dir) / "versions" / version_id
    if not vdir.is_dir():
        return False
    raw = _read_raw_json(vdir, version_id)
    if raw is None:
        return False
    # 自己就有 jar：只要不是空壳就算装好（原版、整合包都是这种）
    for p in vdir.glob("*.jar"):
        try:
            if p.is_file() and p.stat().st_size > 0:
                return True
        except OSError:
            continue
    # 没有自己的 jar：可能是加载器 profile（Fabric/Quilt）或整合包实例，
    # jar 在该版本目录之外，顺着父链找到真正持有 jar 的那一层再判。
    owner = version_id
    node = raw
    seen: set[str] = {version_id}
    while True:
        parent = str(node.get("inheritsFrom") or "")
        if not parent:
            break
        if parent in seen:
            return False
        seen.add(parent)
        pdir = Path(game_dir) / "versions" / parent
        if not pdir.is_dir():
            return False
        node = _read_raw_json(pdir, parent)
        if node is None:
            return False
        owner = parent
    odir = Path(game_dir) / "versions" / owner
    return _has_jar(odir)


def list_installed_versions(game_dir: Path) -> list[str]:
    vdir = Path(game_dir) / "versions"
    if not vdir.is_dir():
        return []
    out: list[str] = []
    try:
        names = [p.name for p in vdir.iterdir() if p.is_dir()]
    except OSError:
        return []
    for name in names:
        try:
            if version_complete(game_dir, name):
                out.append(name)
        except OSError:
            continue
    out.sort(key=_version_sort_key, reverse=True)
    return out


def _version_sort_key(name: str) -> tuple:
    """按版本号自然排序：1.20.1 > 1.9 > 1.20（字符串排序会把 1.9 排到最前）。"""
    parts: list[tuple[int, Any]] = []
    for chunk in name.lower().replace("_", ".").replace("-", ".").split("."):
        if chunk.isdigit():
            parts.append((0, int(chunk)))
        else:
            parts.append((1, chunk))
    return (len(parts), parts, name.lower())


def version_meta(game_dir: Path, version_id: str) -> dict[str, Any]:
    vdir = Path(game_dir) / "versions" / version_id
    if not vdir.is_dir():
        return {"id": version_id, "type": "?", "mainClass": "?", "javaVersion": None,
                "has_jar": False, "jar_size": 0}
    try:
        launcher = GameLauncher(game_dir)
        data = launcher.load_version(version_id)
        jar = launcher.version_jar(version_id, data)
    except LaunchError:
        data = read_version_json(vdir, version_id) or read_client_json(vdir) or {}
        jar = jar_path_of(vdir, data)
    return {
        "id": version_id,
        "type": data.get("type", "?"),
        "mainClass": data.get("mainClass", "?"),
        "javaVersion": (data.get("javaVersion") or {}).get("majorVersion"),
        "has_jar": jar is not None,
        "jar_size": jar.stat().st_size if jar else 0,
        "inherits": data.get("inheritsFrom") or "",
    }
