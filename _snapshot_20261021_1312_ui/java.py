"""Java 运行时检测。

策略：
    1. 用户在设置里指定的路径优先；
    2. 扫描 JAVA_HOME、PATH、常见安装目录；
    3. 扫描启动器自带的 runtime 目录（.minecraft/runtime、PCL/Java 等）；
    4. 逐个执行 `java -version` 解析主版本号与位数。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

_VERSION_RE = re.compile(r'version\s+"?([\d][\d._]*)', re.IGNORECASE)


@dataclass
class JavaInfo:
    path: Path                 # java.exe
    home: Path                 # JDK/JRE 根目录
    version: str = ""          # 原始版本串，如 17.0.2
    major: int = 0             # 主版本 8 / 17 / 21
    bits: int = 64
    vendor: str = ""

    @property
    def label(self) -> str:
        return f"Java {self.major}  ({self.version})  {self.bits}位"


def _run_java(exe: Path) -> JavaInfo | None:
    try:
        proc = subprocess.run(
            [str(exe), "-version"],
            capture_output=True,
            timeout=12,
            creationflags=_CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = (proc.stderr or b"").decode("utf-8", "replace") + \
           (proc.stdout or b"").decode("utf-8", "replace")
    if not text.strip():
        return None
    m = _VERSION_RE.search(text)
    if not m:
        return None
    raw = m.group(1).rstrip("._")
    parts = re.split(r"[._+-]", raw)
    try:
        major = int(parts[0])
        if major == 1 and len(parts) > 1:      # 1.8.0_333 -> 8
            major = int(parts[1])
    except (ValueError, IndexError):
        return None
    bits = 64 if "64-Bit" in text or "64位" in text else 32
    vendor = ""
    for name in ("Temurin", "AdoptOpenJDK", "Oracle", "OpenJDK", "Zulu", "GraalVM", "Microsoft"):
        if name.lower() in text.lower():
            vendor = name
            break
    home = exe.parent.parent if exe.parent.name.lower() in ("bin",) else exe.parent
    return JavaInfo(path=exe, home=home, version=raw, major=major, bits=bits, vendor=vendor)


def _java_exe(base: Path) -> Path | None:
    for rel in ("bin/java.exe", "bin/java", "jre/bin/java.exe", "jre/bin/java"):
        p = base / rel
        if p.is_file():
            return p
    return None


def candidate_homes(game_dir: Path | None = None) -> list[Path]:
    """收集可能含有 java 的目录。"""
    homes: list[Path] = []
    env = os.environ

    for var in ("JAVA_HOME", "JDK_HOME", "JRE_HOME"):
        v = env.get(var)
        if v:
            homes.append(Path(v))

    which = shutil.which("java")
    if which:
        homes.append(Path(which).parent.parent)

    if sys.platform == "win32":
        bases = [
            r"C:\Program Files\Java",
            r"C:\Program Files\Eclipse Adoptium",
            r"C:\Program Files\Microsoft\jdk",
            r"C:\Program Files\Zulu",
            r"C:\Program Files (x86)\Java",
            r"C:\Program Files\BellSoft",
            r"C:\Program Files\Amazon Corretto",
        ]
        for b in bases:
            p = Path(b)
            if p.is_dir():
                try:
                    for sub in p.iterdir():
                        if sub.is_dir():
                            homes.append(sub)
                except OSError:
                    pass

    # 启动器自带运行时
    if game_dir:
        homes.extend(_launcher_runtimes(game_dir))
        homes.extend(_launcher_runtimes(game_dir.parent))

    # 官方启动器 / PCL 的默认运行时目录（与当前游戏目录无关也要扫）
    if sys.platform == "win32":
        appdata = env.get("APPDATA")
        localappdata = env.get("LOCALAPPDATA")
        for base in (appdata, localappdata):
            if not base:
                continue
            mc = Path(base) / ".minecraft"
            if mc.is_dir():
                homes.extend(_launcher_runtimes(mc))
    else:
        mc = Path.home() / ".minecraft"
        if mc.is_dir():
            homes.extend(_launcher_runtimes(mc))

    # 去重保序
    seen: set[str] = set()
    out: list[Path] = []
    for h in homes:
        key = str(h).lower()
        if key not in seen:
            seen.add(key)
            out.append(h)
    return out


def _launcher_runtimes(root: Path) -> list[Path]:
    """扫描常见启动器的 Java 运行时目录。"""
    out: list[Path] = []
    patterns = [
        "runtime/*/bin",
        "runtime/*/*/bin",
        ".minecraft/runtime/*/bin",
        "PCL/Java/*/bin",
        "HMCL/java/*/*/bin",
        "java/*/bin",
    ]
    for pat in patterns:
        try:
            for p in root.glob(pat):
                if p.is_dir():
                    out.append(p.parent)
        except (OSError, ValueError):
            continue
    return out


def detect_all(game_dir: Path | None = None, extra: str = "") -> list[JavaInfo]:
    """返回去重后的 Java 列表，按主版本升序。"""
    found: list[JavaInfo] = []
    seen: set[str] = set()

    homes: list[Path] = []
    if extra:
        p = Path(extra)
        homes.append(p if p.is_dir() else p.parent)
    homes.extend(candidate_homes(game_dir))

    for home in homes:
        exe = _java_exe(home)
        if not exe:
            continue
        key = str(exe).lower()
        if key in seen:
            continue
        seen.add(key)
        info = _run_java(exe)
        if info:
            found.append(info)

    found.sort(key=lambda j: (j.major, j.bits))
    return found


def pick_for_version(javas: list[JavaInfo], required_major: int) -> JavaInfo | None:
    """为某个 MC 版本挑最合适的 Java：优先刚好够用且位数匹配的。"""
    if not javas:
        return None
    ok = [j for j in javas if j.major >= required_major]
    if not ok:
        return max(javas, key=lambda j: j.major)
    ok.sort(key=lambda j: (j.major, -j.bits))
    for j in ok:
        if j.bits == 64:
            return j
    return ok[0]


def required_java(version_json: dict) -> int:
    """版本要求的 Java 主版本。"""
    jv = version_json.get("javaVersion") or {}
    try:
        return int(jv.get("majorVersion") or 0) or _guess_from_id(version_json.get("id", ""))
    except (TypeError, ValueError):
        return _guess_from_id(version_json.get("id", ""))


def _guess_from_id(vid: str) -> int:
    if not vid.startswith("1."):
        return 21
    try:
        minor = int(vid.split(".")[1])
    except (ValueError, IndexError):
        return 8
    if minor >= 21:
        return 21
    if minor >= 18:
        return 17
    if minor >= 17:
        return 16
    return 8
