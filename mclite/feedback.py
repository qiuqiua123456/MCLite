"""一键反馈：把排查问题需要的日志、崩溃报告、模组清单和系统信息打成一个 zip。

给作者发一个文件，比让用户来回截图、翻目录要靠谱得多；顺便把配置里的
令牌字段抹掉，避免把正版账号一起发出去。
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import platform
import shutil
import sys
import zipfile
from pathlib import Path

_SECRET_KEYS = {"access_token", "refresh_token", "ms_account", "accounts", "uuid"}


def desktop_dir() -> Path:
    for name in ("Desktop", "桌面"):
        p = Path.home() / name
        if p.is_dir():
            return p
    return Path.home()


def _total_memory_gb() -> float:
    """Windows 上没有 os.sysconf，用 GlobalMemoryStatusEx 取物理内存总量。"""
    if sys.platform != "win32":
        try:
            return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024 ** 3
        except (AttributeError, ValueError, OSError):
            return 0.0
    import ctypes

    class _MemStatus(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = _MemStatus()
    status.dwLength = ctypes.sizeof(_MemStatus)
    try:
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return status.ullTotalPhys / 1024 ** 3
    except (AttributeError, OSError):
        pass
    return 0.0


def _program_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _sysinfo_lines(cfg, javas=None) -> list[str]:
    total_gb = _total_memory_gb()
    lines = [
        f"时间: {_dt.datetime.now():%Y-%m-%d %H:%M:%S}",
        f"系统: {platform.platform()}",
        f"CPU: {platform.processor() or '未知'}（{os.cpu_count()} 线程）",
        f"内存: {total_gb:.1f} GB" if total_gb else "内存: 未知",
        f"Python: {sys.version.split()[0]} ({platform.architecture()[0]})",
        f"程序目录: {_program_dir()}",
        f"游戏目录: {cfg.get('game_dir')}",
        f"分配的 Java 路径: {cfg.get('java_path') or '（自动检测）'}",
        f"内存设置: {cfg.get('memory_mb')} MB",
        f"下载源: {cfg.get('download_source')}",
        "",
        "检测到的 Java:",
    ]
    if javas:
        for j in javas:
            lines.append(f"  {j.label}  {j.path}")
    else:
        lines.append("  （未提供）")
    return lines


def _mod_list(game_dir: str | Path) -> str:
    mods = Path(game_dir) / "mods"
    if not mods.is_dir():
        return "（没有 mods 文件夹）\n"
    rows = ["文件名\t大小\tSHA1(前16位)"]
    for p in sorted(mods.iterdir(), key=lambda x: x.name.lower()):
        if not p.is_file() or p.suffix.lower() not in (".jar", ".zip", ".disabled"):
            continue
        try:
            size = p.stat().st_size
            digest = ""
            if p.stat().st_size <= 40 * 1024 * 1024:
                h = hashlib.sha1()
                with open(p, "rb") as fh:
                    for chunk in iter(lambda: fh.read(1 << 20), b""):
                        h.update(chunk)
                digest = h.hexdigest()[:16]
            rows.append(f"{p.name}\t{size}\t{digest}")
        except OSError:
            continue
    return "\n".join(rows) + "\n"


def _sanitized_cfg(cfg) -> str:
    data = {}
    for k, v in dict(cfg._data).items():        # noqa: SLF001  (配置对象的内部字典)
        if k in _SECRET_KEYS:
            continue
        data[k] = v
    return json.dumps(data, ensure_ascii=False, indent=2)


def _recent(folder: Path, patterns: tuple[str, ...], keep: int) -> list[Path]:
    if not folder.is_dir():
        return []
    found: list[Path] = []
    for pattern in patterns:
        found.extend(p for p in folder.glob(pattern) if p.is_file())
    found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return found[:keep]


def collect(cfg, javas=None, dest_dir: Path | None = None,
            game_dir: str | Path | None = None) -> Path:
    """打包并返回 zip 路径。"""
    game_dir = Path(game_dir or cfg.get("game_dir") or ".")
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = dest_dir or desktop_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"MCLite反馈_{stamp}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("系统信息.txt", "\n".join(_sysinfo_lines(cfg, javas)) + "\n")
        zf.writestr("配置.json", _sanitized_cfg(cfg))
        zf.writestr("模组清单.txt", _mod_list(game_dir))

        logs_dir = game_dir / "logs"
        for p in _recent(logs_dir, ("mclite-*.log", "latest.log"), keep=3):
            _add(zf, p, f"日志/{p.name}")

        crash_dir = game_dir / "crash-reports"
        for p in _recent(crash_dir, ("crash-*.txt",), keep=3):
            _add(zf, p, f"崩溃报告/{p.name}")

        launcher_cfg = Path(cfg.path).parent if hasattr(cfg, "path") else None
        if launcher_cfg and launcher_cfg.is_dir():
            for p in _recent(launcher_cfg, ("*.log",), keep=2):
                _add(zf, p, f"启动器日志/{p.name}")
    return zip_path


def _add(zf: zipfile.ZipFile, path: Path, arcname: str, limit: int = 4 * 1024 * 1024) -> None:
    """大日志只留尾巴，避免反馈包几十 MB。"""
    try:
        if path.stat().st_size <= limit:
            zf.write(path, arcname)
            return
        with open(path, "rb") as fh:
            fh.seek(0, 2)
            fh.seek(max(0, fh.tell() - limit))
            tail = fh.read()
        zf.writestr(arcname, "……（已截断，只保留最后 4 MB）……\n".encode("utf-8") + tail)
    except OSError:
        pass


def copy_dir(src: Path, dst: Path) -> None:
    """留个口子：以后要把实例整包导出时用得上。"""
    shutil.copytree(src, dst, dirs_exist_ok=True)
