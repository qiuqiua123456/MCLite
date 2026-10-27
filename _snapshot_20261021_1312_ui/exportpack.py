"""把已安装的版本 / 整合包实例导出成 Modrinth ``.mrpack``。

:mod:`mclite.modpack` 负责把 ``.mrpack`` 装成一个独立版本，这里做反向操作：
收集实例目录里的 ``mods``、``config``、``options.txt`` 等，原样塞进压缩包的
``overrides/``，再写一份 ``modrinth.index.json`` 声明 Minecraft 与加载器版本。
导出的包可以直接被 PCL、Modrinth App 等支持 ``.mrpack`` 的启动器导入。
"""

from __future__ import annotations

import json
import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from . import instances
from .downloader import human_size
from .launcher import GameLauncher
from .modpack import INDEX_NAME, safe_name

#: 加载器种类 → ``modrinth.index.json`` 里的依赖键
LOADER_KEYS = {
    "fabric": "fabric-loader",
    "quilt": "quilt-loader",
    "forge": "forge",
    "neoforge": "neoforge",
}

#: 加载器种类 → 界面上显示的名字
LOADER_NAMES = {
    "fabric": "Fabric",
    "quilt": "Quilt",
    "forge": "Forge",
    "neoforge": "NeoForge",
}

#: 压缩包里放覆盖文件的目录名
OVERRIDES = "overrides"

#: 除 mods / config 外固定收集的根目录文件（存在才打）
EXTRA_FILES = ("options.txt", "servers.dat")

#: 又大又跟整合包无关的目录，遍历时直接跳过
SKIP_DIRS = {".cache", "logs", "crash-reports", "screenshots"}

#: 版本 id 里常见的加载器写法：(正则, 加载器种类)
_ID_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"neoforge-(?P<loader>[0-9][0-9A-Za-z.+]*)$", re.I), "neoforge"),
    (re.compile(r"fabric-loader-(?P<loader>[0-9][0-9A-Za-z.+]*)-(?P<mc>\d.*)$", re.I), "fabric"),
    (re.compile(r"quilt-loader-(?P<loader>[0-9][0-9A-Za-z.+-]*)-(?P<mc>\d.*)$", re.I), "quilt"),
    (re.compile(r"(?<![\w.-])forge-(?P<mc>\d+\.\d+(?:\.\d+)?)-(?P<loader>[0-9][0-9A-Za-z.+]*)$",
                re.I), "forge"),
    (re.compile(r"(?<![\w.-])(?P<mc>\d+\.\d+(?:\.\d+)?)-forge-(?P<loader>[0-9][0-9A-Za-z.+]*)$",
                re.I), "forge"),
)

#: libraries 里表示加载器的坐标
_LOADER_LIBS = {
    "net.fabricmc:fabric-loader": "fabric",
    "net.fabricmc:loader": "fabric",
    "org.quiltmc:quilt-loader": "quilt",
    "net.minecraftforge:forge": "forge",
    "net.minecraftforge:fmlloader": "forge",
    "net.neoforged:neoforge": "neoforge",
}

#: 像 Minecraft 版本号的字符串（1.20.1 / 1.20 / 1.20.5-pre1 / 24w14a）
_MC_LIKE = re.compile(
    r"^\d+\.\d+(?:\.\d+)?(?:[-_](?:pre|rc)\d+)?$|^\d{2}w\d{2}[a-z]$", re.I)

_LOG = Callable[[str], None]


@dataclass
class ExportResult:
    """一次导出的结果。"""

    path: Path
    files: int
    bytes: int
    mc_version: str
    loader_kind: str
    loader_version: str

    def summary(self) -> str:
        """给用户看的一行结果。"""
        loader = ""
        if self.loader_kind:
            name = LOADER_NAMES.get(self.loader_kind, self.loader_kind)
            loader = f"，{name} {self.loader_version}".rstrip()
        return (f"已导出 {self.path.name}：{self.files} 个文件，"
                f"{human_size(self.bytes)}，Minecraft {self.mc_version}{loader}")


def _split_forge_version(text: str) -> tuple[str, str]:
    """``1.20.1-47.3.1`` → ``("1.20.1", "47.3.1")``；只有构建号时 MC 版本留空。"""
    text = (text or "").strip()
    m = re.match(r"^(?P<mc>\d+\.\d+(?:\.\d+)?)-(?P<loader>.+)$", text)
    if m:
        return m.group("mc"), m.group("loader")
    return "", text


def _mc_from_neoforge(version: str) -> str:
    """NeoForge 版本号编码了 MC 版本：``20.4.237`` → ``1.20.4``，``21.1.80`` → ``1.21.1``。"""
    m = re.match(r"^(\d+)\.(\d+)", version or "")
    if not m:
        return ""
    return f"1.{m.group(1)}.{m.group(2)}"


def _fml_args(vjson: dict[str, Any]) -> dict[str, str]:
    """Forge / NeoForge 写在启动参数里的版本号（合并后的 JSON 常只剩这一份线索）。"""
    out: dict[str, str] = {}
    args = vjson.get("arguments")
    if not isinstance(args, dict):
        return out
    game = args.get("game")
    if not isinstance(game, list):
        return out
    wanted = ("--fml.mcVersion", "--fml.forgeVersion", "--fml.neoForgeVersion")
    for i, arg in enumerate(game[:-1]):
        if isinstance(arg, str) and arg in wanted:
            value = game[i + 1]
            if isinstance(value, str) and value:
                out[arg] = value
    return out


def _parent_hint(game_dir: Path, version_id: str) -> str:
    """版本目录里直接写的 ``inheritsFrom``（合并后的 JSON 里这个字段已经被消掉）。"""
    vdir = Path(game_dir) / "versions" / version_id
    if not vdir.is_dir():
        return ""
    for path in sorted(vdir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            parent = str(data.get("inheritsFrom") or "").strip()
            if parent:
                return parent
    return ""


def detect_dependencies(game_dir: Path, version_id: str,
                        vjson: dict[str, Any]) -> tuple[str, str, str]:
    """猜出 ``(Minecraft 版本, 加载器种类, 加载器版本)``，例如 ``("1.20.1", "fabric", "0.19.5")``。

    先看版本 id 里的命名（``fabric-loader-<ver>-<mc>``、``forge-<mc>-<build>`` 等），
    再看 ``libraries`` 里的加载器坐标；仍然确定不了就退回版本 id，加载器留空。
    ``game_dir`` 只在需要回查版本目录里的 ``inheritsFrom`` 时用到。
    """
    data = vjson if isinstance(vjson, dict) else {}
    vid = str(data.get("id") or version_id or "").strip()

    mc_version = ""
    loader_kind = ""
    loader_version = ""

    # 1. 版本 id 命名
    for pattern, kind in _ID_RULES:
        match = pattern.search(vid)
        if not match:
            continue
        groups = match.groupdict()
        loader_kind = kind
        loader_version = (groups.get("loader") or "").strip()
        mc_version = (groups.get("mc") or "").strip()
        break

    # 2. libraries 里的加载器坐标
    if not loader_kind:
        for lib in data.get("libraries") or []:
            if not isinstance(lib, dict):
                continue
            parts = str(lib.get("name") or "").split(":")
            if len(parts) < 3:
                continue
            lib_kind = _LOADER_LIBS.get(f"{parts[0]}:{parts[1]}".lower())
            if not lib_kind:
                continue
            version = parts[2].strip()
            loader_kind = lib_kind
            if lib_kind in ("forge", "neoforge"):
                mc_version, loader_version = _split_forge_version(version)
                if not loader_version:
                    loader_version = version
            else:
                loader_version = version
            break

    # 有些启动器把 Forge 的 libraries 精简掉了，只剩启动参数里的版本号
    fml = _fml_args(data)
    if not loader_kind:
        if fml.get("--fml.neoForgeVersion"):
            loader_kind = "neoforge"
            loader_version = fml["--fml.neoForgeVersion"]
        elif fml.get("--fml.forgeVersion"):
            loader_kind = "forge"
            loader_version = fml["--fml.forgeVersion"]
    if loader_kind and not loader_version:
        if loader_kind == "forge":
            loader_version = fml.get("--fml.forgeVersion", "")
        elif loader_kind == "neoforge":
            loader_version = (fml.get("--fml.neoForgeVersion")
                              or fml.get("--fml.forgeVersion") or "")
    if loader_kind and not mc_version:
        mc_version = fml.get("--fml.mcVersion", "")

    # 3. Minecraft 版本的回退：父版本 → 版本目录 → NeoForge 编码 → 版本 id
    if not mc_version:
        jar_from = str(data.get("_jar_from") or "").strip()
        if _MC_LIKE.match(jar_from):
            mc_version = jar_from
    if not mc_version:
        parent = _parent_hint(game_dir, version_id)
        if _MC_LIKE.match(parent):
            mc_version = parent
    if not mc_version and loader_kind == "neoforge":
        mc_version = _mc_from_neoforge(loader_version)
    if not mc_version:
        mc_version = vid if _MC_LIKE.match(vid) else str(data.get("id") or version_id or "")
    return mc_version, loader_kind, loader_version


def _source_root(game_dir: Path, version_id: str) -> Path:
    """导出时从哪个目录收集内容。

    版本目录本身就是隔离实例（里面躺着 mods / config / options.txt 等）时用它，
    否则用共用游戏目录。``instances.effective(..., True)`` 只表示「调用方要求
    隔离」，对只有 jar / json 的原版版本目录也会返回真，所以还要确认目录里确实
    有实例内容，免得导出个空包。
    """
    version_dir = instances.instance_dir(game_dir, version_id)
    if not instances.effective(game_dir, version_id, True):
        return Path(game_dir)
    if instances.is_isolated(game_dir, version_id):
        return version_dir
    for name in EXTRA_FILES:
        try:
            if (version_dir / name).is_file():
                return version_dir
        except OSError:
            continue
    return Path(game_dir)


def _same_path(left: Path, right: Path) -> bool:
    """两个路径是否指向同一个文件（避免把正在写的 zip 自己也打进去）。"""
    try:
        return (os.path.normcase(os.path.abspath(left))
                == os.path.normcase(os.path.abspath(right)))
    except OSError:
        return False


def _collect_files(root: Path, dest: Path, *, include_saves: bool, include_config: bool,
                   include_resourcepacks: bool) -> list[tuple[Path, str, int]]:
    """列出要放进 ``overrides/`` 的文件，返回 ``[(源路径, 相对路径, 字节数)]``。"""
    dirs = ["mods"]
    if include_config:
        dirs.append("config")
    if include_saves:
        dirs.append("saves")
    if include_resourcepacks:
        dirs.append("resourcepacks")

    items: list[tuple[Path, str, int]] = []
    for sub in dirs:
        base = root / sub
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            for filename in sorted(filenames):
                full = Path(dirpath) / filename
                if _same_path(full, dest):
                    continue
                try:
                    size = full.stat().st_size
                    rel = full.relative_to(root).as_posix()
                except (OSError, ValueError):
                    continue
                items.append((full, rel, size))

    for name in EXTRA_FILES:
        full = root / name
        try:
            if not full.is_file() or _same_path(full, dest):
                continue
            size = full.stat().st_size
        except OSError:
            continue
        items.append((full, name, size))

    items.sort(key=lambda item: item[1].lower())
    return items


def _report(progress_cb: Callable[[int, int], None] | None, done: int, total: int) -> None:
    """调用进度回调；回调出错不能把导出带崩。"""
    if progress_cb is None:
        return
    try:
        progress_cb(done, total)
    except Exception:                                    # noqa: BLE001
        pass


def export_pack(
    game_dir: Path,
    version_id: str,
    dest_zip: Path,
    *,
    include_saves: bool = False,
    include_config: bool = True,
    include_resourcepacks: bool = False,
    name: str = "",
    on_log: _LOG = lambda _m: None,
    progress_cb: Callable[[int, int], None] | None = None,
) -> ExportResult:
    """把一个实例打包成 ``.mrpack``。

    ``dest_zip`` 是目标文件；传目录时按包名自动起名 ``<包名>.mrpack``。
    ``name`` 为空就用版本 id。内容全部放进 ``overrides/``（``files`` 留空，
    不需要联网下载），加载器版本写进 ``dependencies``。
    """
    game_dir = Path(game_dir)
    version_id = str(version_id or "").strip()
    if not version_id:
        raise ValueError("版本 id 不能为空")

    vjson = GameLauncher(game_dir).load_version(version_id)
    mc_version, loader_kind, loader_version = detect_dependencies(
        game_dir, version_id, vjson)

    root = _source_root(game_dir, version_id)
    title = (name or "").strip() or version_id

    dest = Path(dest_zip)
    if dest.is_dir():
        dest = dest / f"{safe_name(title)}.mrpack"
    dest.parent.mkdir(parents=True, exist_ok=True)

    dependencies: dict[str, str] = {"minecraft": mc_version}
    if loader_kind and loader_version:
        dependencies[LOADER_KEYS[loader_kind]] = loader_version
    index = {
        "formatVersion": 1,
        "game": "minecraft",
        "versionId": title,
        "name": title,
        "summary": "由 MCLite 导出",
        "files": [],
        "dependencies": dependencies,
    }

    files = _collect_files(
        root,
        dest,
        include_saves=include_saves,
        include_config=include_config,
        include_resourcepacks=include_resourcepacks,
    )
    loader_note = ""
    if loader_kind:
        loader_note = f"，{LOADER_NAMES.get(loader_kind, loader_kind)} {loader_version}".rstrip()
    on_log(f"导出 {version_id} → {dest.name}（Minecraft {mc_version}{loader_note}，"
           f"{len(files)} 个文件）")
    on_log(f"内容目录：{root}")

    total = len(files)
    written = 0
    total_bytes = 0
    try:
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(INDEX_NAME, json.dumps(index, ensure_ascii=False, indent=2).encode("utf-8"))
            for done, (src, rel, size) in enumerate(files, 1):
                arcname = f"{OVERRIDES}/{rel}"
                try:
                    zf.write(src, arcname=arcname)
                except OSError as exc:
                    on_log(f"跳过 {rel}：{exc}")
                    _report(progress_cb, done, total)
                    continue
                written += 1
                total_bytes += size
                on_log(f"打包 {arcname}")
                _report(progress_cb, done, total)
    except Exception:
        try:
            dest.unlink()
        except OSError:
            pass
        raise

    if not files:
        on_log("没有可打包的内容（检查实例目录，或打开 include_saves / include_resourcepacks）")
    on_log(f"导出完成：{dest}")
    return ExportResult(
        path=dest,
        files=written,
        bytes=total_bytes,
        mc_version=mc_version,
        loader_kind=loader_kind,
        loader_version=loader_version,
    )
