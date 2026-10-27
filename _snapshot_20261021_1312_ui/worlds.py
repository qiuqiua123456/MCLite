"""存档（世界）管理：列表、查看大小/时间、备份 zip、从备份恢复、删除、打开目录。

``saves`` 下每个带 ``level.dat`` 的子目录算一个存档。显示名与版本名都来自
``level.dat``（gzip 压缩的 NBT），这里只用标准库手写了一个极简 NBT 读取器，
只认 ``LevelName`` 与 ``Version.Name``；存档损坏或格式不认识时静默回退到目录名，
绝不因为解析失败让界面报错。
"""

from __future__ import annotations

import gzip
import os
import re
import shutil
import struct
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .downloader import human_size
from .mods import open_folder as _open_folder

LEVEL_DAT = "level.dat"
ICON_NAME = "icon.png"
SESSION_LOCK = "session.lock"

#: Windows 文件名非法字符
_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# ---------------------------------------------------------------- 数据结构


@dataclass
class World:
    name: str                # 显示名（优先读 level.dat 的 LevelName，读不到就用目录名）
    folder: str              # 目录名
    path: Path
    size: int
    mtime: float
    version: str = ""        # 从 level.dat 里解析出的版本名，失败留空
    has_icon: bool = False

    @property
    def size_text(self) -> str:
        return human_size(float(self.size))

    def mtime_text(self) -> str:
        if self.mtime <= 0:
            return "—"
        try:
            return datetime.fromtimestamp(self.mtime).strftime("%Y-%m-%d %H:%M")
        except (OSError, OverflowError, ValueError):
            return "—"


# ---------------------------------------------------------------- 对外接口


def worlds_dir(base_dir: Path) -> Path:
    """存档根目录：``<游戏目录>/saves``。"""
    return Path(base_dir) / "saves"


def list_worlds(base_dir: Path) -> list[World]:
    """列出所有存档，按最后修改时间倒序。目录不存在或没有存档时返回空列表。"""
    d = worlds_dir(base_dir)
    try:
        if not d.is_dir():
            return []
        children = list(d.iterdir())
    except OSError:
        return []

    out: list[World] = []
    for child in children:
        try:
            if not child.is_dir():
                continue
        except OSError:
            continue
        world = _build_world(child)
        if world is not None:
            out.append(world)
    out.sort(key=lambda w: (w.mtime, w.folder.lower()), reverse=True)
    return out


def backup(world: World, dest_dir: Path | None = None,
           on_log: Callable[[str], None] = lambda _m: None,
           progress_cb: Callable[[float], None] | None = None) -> Path:
    """把存档打包成 zip，返回 zip 路径。

    - 文件名：``世界名_YYYYmmdd_HHMMSS.zip``，默认存到 ``<游戏目录>/mclite-backups``。
    - zip 内第一层就是存档目录名，``session.lock`` 跳过（运行时的锁，备份没意义）。
    - ``progress_cb`` 收到 0.0~1.0 的已写入文件比例。
    """
    folder = Path(world.path)
    if not folder.is_dir():
        raise OSError(f"存档目录不存在：{folder}")
    base_dir = folder.parent.parent                 # saves 的上一级 = 游戏目录
    dest = Path(dest_dir) if dest_dir is not None else backups_dir(base_dir)
    dest.mkdir(parents=True, exist_ok=True)

    safe = _safe_name(world.name or world.folder)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = dest / f"{safe}_{stamp}.zip"
    index = 1
    while zip_path.exists():                        # 同一秒内重复备份不覆盖
        zip_path = dest / f"{safe}_{stamp}_{index}.zip"
        index += 1

    files: list[tuple[Path, str]] = []
    total_bytes = 0
    for root, _dirs, names in os.walk(folder):
        for fname in names:
            if fname.lower() == SESSION_LOCK:
                continue
            src = Path(root) / fname
            try:
                size = src.stat().st_size
            except OSError:
                size = 0
            rel = src.relative_to(folder).as_posix()
            files.append((src, f"{world.folder}/{rel}"))
            total_bytes += size

    on_log(f"备份存档 {world.name}：{len(files)} 个文件，{human_size(float(total_bytes))}")
    total = len(files) or 1
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
            for count, (src, arc) in enumerate(files, 1):
                try:
                    zf.write(src, arc)
                except OSError as exc:              # 单个文件被占用就跳过，不毁整包
                    on_log(f"跳过 {arc}：{exc}")
                if progress_cb is not None:
                    progress_cb(count / total)
    except OSError:
        try:
            zip_path.unlink()
        except OSError:
            pass
        raise
    on_log(f"已备份到 {zip_path}")
    return zip_path


def restore(zip_path: Path, base_dir: Path) -> tuple[bool, str]:
    """把备份 zip 解到 ``saves/`` 下，返回 ``(成功, 提示)``。

    zip 里第一层目录名就是还原后的存档目录名；如果 ``saves/`` 下已存在同名目录，
    会依次改用 ``xxx_恢复``、``xxx_恢复2`` …，绝不覆盖正在玩的存档。
    """
    src = Path(zip_path)
    if not src.is_file():
        return False, f"备份不存在：{src}"

    saves = worlds_dir(base_dir)
    try:
        saves.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, f"无法创建 saves 目录：{exc}"

    try:
        with zipfile.ZipFile(src) as zf:
            members = [info for info in zf.infolist() if not info.filename.endswith("/")]
            if not members:
                return False, "备份是空的"

            names = [_split_parts(info.filename) for info in members]
            tops = {parts[0] for parts in names if parts}
            shared = next(iter(tops)) if len(tops) == 1 else ""   # 唯一的顶层目录名
            folder = _safe_name(shared or src.stem)

            target = saves / folder
            if target.exists():
                candidate = saves / f"{folder}_恢复"
                index = 2
                while candidate.exists():
                    candidate = saves / f"{folder}_恢复{index}"
                    index += 1
                target = candidate

            try:
                for info, parts in zip(members, names):
                    if not parts:
                        continue
                    inner = parts[1:] if shared and parts[0] == shared else parts
                    if not inner:
                        continue
                    out = target.joinpath(*inner)
                    out.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info) as fsrc, open(out, "wb") as fdst:
                        shutil.copyfileobj(fsrc, fdst, 1 << 20)
            except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
                shutil.rmtree(target, ignore_errors=True)          # 别留半个存档
                return False, f"恢复失败：{exc}"
    except zipfile.BadZipFile:
        return False, "不是有效的 zip 备份"
    except OSError as exc:
        return False, f"读取备份失败：{exc}"
    return True, f"已恢复到 saves/{target.name}"


def delete(world: World) -> tuple[bool, str]:
    """删除一个存档，返回 ``(成功, 提示/错误)``。"""
    try:
        shutil.rmtree(Path(world.path))
        return True, f"已删除 {world.name}"
    except OSError as exc:
        return False, str(exc)


def backups_dir(base_dir: Path) -> Path:
    """备份目录：``<游戏目录>/mclite-backups``。"""
    return Path(base_dir) / "mclite-backups"


def list_backups(base_dir: Path) -> list[Path]:
    """列出备份 zip，按修改时间倒序（新备份在前）。"""
    d = backups_dir(base_dir)
    try:
        if not d.is_dir():
            return []
        files = [p for p in d.iterdir() if p.is_file() and p.suffix.lower() == ".zip"]
    except OSError:
        return []
    files.sort(key=lambda p: _mtime(p), reverse=True)
    return files


def open_folder(path: Path) -> None:
    """在系统文件管理器里打开目录（复用 :func:`mclite.mods.open_folder`）。"""
    _open_folder(Path(path))


# ---------------------------------------------------------------- 内部工具


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _safe_name(name: str) -> str:
    """把显示名变成合法文件名/目录名（保留中文，替换 Windows 非法字符）。"""
    text = _BAD_CHARS.sub("_", (name or "世界").strip())
    text = text.strip(" .")
    return text[:60] or "世界"


def _split_parts(name: str) -> list[str]:
    """拆 zip 成员路径；含 ``..`` 或盘符的成员一律拒绝（防路径穿越）。"""
    parts = [p for p in name.replace("\\", "/").split("/") if p not in ("", ".")]
    if any(p == ".." or p.endswith(":") for p in parts):
        return []
    return parts


def _scan_size(folder: Path) -> tuple[int, float]:
    """递归求和目录大小，顺带取最新文件修改时间；跳过 session.lock。"""
    total = 0
    newest = 0.0
    try:
        for root, _dirs, files in os.walk(folder):
            for fname in files:
                if fname.lower() == SESSION_LOCK:
                    continue
                try:
                    st = os.stat(os.path.join(root, fname))
                except OSError:
                    continue
                total += st.st_size
                if st.st_mtime > newest:
                    newest = st.st_mtime
    except OSError:
        pass
    return total, newest


def _build_world(folder: Path) -> World | None:
    """目录 → World；没有 level.dat 的不算存档，返回 None。"""
    level = folder / LEVEL_DAT
    try:
        if not level.is_file():
            return None
    except OSError:
        return None

    name, version = _level_info(level)
    size, mtime = _scan_size(folder)
    # 目录被改过（改名、增删文件）也算 "最近动过"
    mtime = max(mtime, _mtime(folder), _mtime(level))
    try:
        has_icon = (folder / ICON_NAME).is_file()
    except OSError:
        has_icon = False

    return World(
        name=name or folder.name,
        folder=folder.name,
        path=folder,
        size=size,
        mtime=mtime,
        version=version,
        has_icon=has_icon,
    )


def _level_info(level_path: Path) -> tuple[str, str]:
    """读 level.dat，返回 ``(LevelName, Version.Name)``，任何失败都返回空串。"""
    data = _load_level_dat(level_path)
    root = data
    # 1.13 以前的 level.dat 把所有字段包在 Data 里，顺手兼容一下老存档
    nested = data.get("Data")
    if isinstance(nested, dict) and "LevelName" not in data and "Version" not in data:
        root = nested

    name = root.get("LevelName")
    if not isinstance(name, str):
        name = ""

    version = ""
    ver = root.get("Version")
    if isinstance(ver, dict):
        vname = ver.get("Name")
        if isinstance(vname, str):
            version = vname.strip()

    return name.strip(), version


def _load_level_dat(level_path: Path) -> dict[str, Any]:
    """读出 gzip 里的 NBT 根 compound；损坏时退回未压缩读取，再失败返回 {}。"""
    try:
        with gzip.open(level_path, "rb") as fh:
            raw = fh.read()
    except Exception:                                       # noqa: BLE001  压缩头损坏
        try:
            raw = Path(level_path).read_bytes()
        except OSError:
            return {}
    try:
        return _parse_nbt(raw)
    except Exception:                                       # noqa: BLE001  解析失败静默回退
        return {}


# ---------------------------------------------------------------- 极简 NBT
#
# 只读不写，够解析 level.dat 即可：gzip 解开后是
# [TAG_Compound][名字长度 i16][名字][若干 tag …][TAG_End]，
# 每个 tag 是 [type u8][名字长度 i16][名字][payload]。

TAG_END = 0
TAG_BYTE = 1
TAG_SHORT = 2
TAG_INT = 3
TAG_LONG = 4
TAG_FLOAT = 5
TAG_DOUBLE = 6
TAG_BYTE_ARRAY = 7
TAG_STRING = 8
TAG_LIST = 9
TAG_COMPOUND = 10
TAG_INT_ARRAY = 11
TAG_LONG_ARRAY = 12

_MAX_DEPTH = 32


class _NbtReader:
    """顺序读取 NBT 的游标；遇到截断/未知类型抛 ValueError。"""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def take(self, n: int) -> bytes:
        end = self.pos + n
        if n < 0 or end > len(self.data):
            raise ValueError("NBT 数据被截断")
        chunk = self.data[self.pos:end]
        self.pos = end
        return chunk

    def skip(self, n: int) -> None:
        end = self.pos + n
        if n < 0 or end > len(self.data):
            raise ValueError("NBT 数据被截断")
        self.pos = end

    def u8(self) -> int:
        return self.take(1)[0]

    def u16(self) -> int:
        return struct.unpack(">H", self.take(2))[0]

    def i16(self) -> int:
        return struct.unpack(">h", self.take(2))[0]

    def i32(self) -> int:
        return struct.unpack(">i", self.take(4))[0]

    def i64(self) -> int:
        return struct.unpack(">q", self.take(8))[0]

    def string(self) -> str:
        return self.take(self.u16()).decode("utf-8", "replace")

    def payload(self, tag_type: int, depth: int = 0) -> Any:
        if tag_type == TAG_BYTE:
            return struct.unpack(">b", self.take(1))[0]
        if tag_type == TAG_SHORT:
            return self.i16()
        if tag_type == TAG_INT:
            return self.i32()
        if tag_type == TAG_LONG:
            return self.i64()
        if tag_type == TAG_FLOAT:
            return struct.unpack(">f", self.take(4))[0]
        if tag_type == TAG_DOUBLE:
            return struct.unpack(">d", self.take(8))[0]
        if tag_type == TAG_STRING:
            return self.string()
        if tag_type == TAG_BYTE_ARRAY:
            n = self.i32()
            self.skip(n)
            return n
        if tag_type == TAG_INT_ARRAY:
            n = self.i32()
            self.skip(n * 4)
            return n
        if tag_type == TAG_LONG_ARRAY:
            n = self.i32()
            self.skip(n * 8)
            return n
        if tag_type == TAG_LIST:
            item_type = self.u8()
            n = self.i32()
            if n <= 0 or item_type == TAG_END:
                return []
            if depth >= _MAX_DEPTH:
                raise ValueError("NBT 嵌套过深")
            return [self.payload(item_type, depth + 1) for _ in range(n)]
        if tag_type == TAG_COMPOUND:
            if depth >= _MAX_DEPTH:
                raise ValueError("NBT 嵌套过深")
            out: dict[str, Any] = {}
            while True:
                t = self.u8()
                if t == TAG_END:
                    return out
                key = self.string()
                out[key] = self.payload(t, depth + 1)
        raise ValueError(f"未知 NBT 类型 {tag_type}")


def _parse_nbt(data: bytes) -> dict[str, Any]:
    """解析一个完整的 NBT 根 compound（level.dat 解压后的字节）。"""
    reader = _NbtReader(data)
    if reader.u8() != TAG_COMPOUND:
        raise ValueError("NBT 根不是 TAG_Compound")
    reader.string()                                     # 根名字，通常为空
    root = reader.payload(TAG_COMPOUND)
    if not isinstance(root, dict):
        raise ValueError("NBT 根不是 compound")
    return root
