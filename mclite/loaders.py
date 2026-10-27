"""Forge / NeoForge / Fabric 加载器的版本列表与安装。

设计取舍：

* **Fabric** —— 官方 meta 提供现成的 profile JSON，本质上就是往
  ``versions/<id>/<id>.json`` 写一份继承原版的版本文件再补齐库，
  所以自己实现，不依赖任何安装器。
* **Forge / NeoForge** —— 官方安装器要做 jar 拆分、SRG 重映射、
  binarypatch 等一系列 processor 步骤，自己重写风险极高，因此直接调用
  官方 installer jar（``--installClient <dir>``）。
* 这台机器上 Python 的 TLS 会被 maven.minecraftforge.net / BMCLAPI 的
  ``/maven/`` 掐断（握手成功、读数据超时），而系统 curl.exe 通常几秒就下完，
  所以 maven 下载都走 :func:`curl_fetch` 兜底。
* BMCLAPI 的 ``/maven/`` 偶尔返回 SHA1 不匹配的坏文件，还会 302 到黑洞节点，
  因此库文件一律按 SHA1 校验，不合格就换官方源。
"""

from __future__ import annotations

import json
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .downloader import (
    DownloadTask, Downloader, curl_fetch, fetch_bytes_robust, fetch_text,
    map_source, sha1_of,
)

KINDS: dict[str, str] = {
    "fabric": "Fabric",
    "quilt": "Quilt",
    "forge": "Forge",
    "neoforge": "NeoForge",
}

BMCLAPI = "https://bmclapi2.bangbang93.com"
FABRIC_META_BMCL = f"{BMCLAPI}/fabric-meta/v2"
FABRIC_META_OFFICIAL = "https://meta.fabricmc.net/v2"
#: Quilt 没有 BMCLAPI 镜像，只能直连官方 meta
QUILT_META = "https://meta.quiltmc.org/v3"
FORGE_MIRROR = f"{BMCLAPI}/maven"

_CREATE_NO_WINDOW = 0x08000000


@dataclass
class LoaderVersion:
    version: str
    stable: bool = True
    note: str = ""

    @property
    def label(self) -> str:
        return f"{self.version}   " + ("正式版" if self.stable else "测试版")


# ---------------------------------------------------------------- 小工具

def _get_json(url: str, timeout: int = 20):
    return json.loads(fetch_text(url, timeout=timeout))


def _fetch_retry(url: str, timeout: int = 60, tries: int = 3) -> str:
    """取文本，失败自动重试。

    meta.quiltmc.org 走的是 Cloudflare，第一条请求要握手 ~6s、偶尔还会
    卡 60~90 秒才吐数据；冷启动时 25 秒默认超时会被掐断。这里放宽超时
    并重试，第二次基本都在 1 秒内返回。
    """
    last: Exception | None = None
    for attempt in range(tries):
        try:
            return fetch_text(url, timeout=timeout)
        except Exception as exc:                     # noqa: BLE001
            last = exc
            if attempt + 1 < tries:
                time.sleep(1.0 + attempt)
    raise RuntimeError(f"请求失败：{url}（{last}）")


def _maven_path(name: str) -> str:
    """``group:artifact:version[:classifier]`` → 仓库内的相对路径。"""
    parts = name.split(":")
    if len(parts) < 3:
        raise ValueError(f"无法解析的 Maven 坐标：{name}")
    group, artifact, version = parts[0], parts[1], parts[2]
    classifier = parts[3] if len(parts) > 3 else ""
    filename = f"{artifact}-{version}" + (f"-{classifier}" if classifier else "") + ".jar"
    return f"{group.replace('.', '/')}/{artifact}/{version}/{filename}"


def _lib_target(lib: dict, default_base: str) -> tuple[str, str]:
    """返回 (下载 URL, 仓库相对路径)。"""
    name = lib.get("name") or ""
    path = _maven_path(name)
    artifact = ((lib.get("downloads") or {}).get("artifact") or {})
    if artifact.get("url"):
        return str(artifact["url"]), artifact.get("path") or path
    base = (lib.get("url") or default_base).rstrip("/")
    return f"{base}/{path}", path


def full_version(kind: str, mc_version: str, version: str) -> str:
    """把列表里的 version 补成完整版本号。"""
    if kind == "forge":
        return version if version.startswith(f"{mc_version}-") else f"{mc_version}-{version}"
    if kind == "neoforge":
        if version.startswith(f"{mc_version}-"):
            return version
        # 1.20.1 的 NeoForge 挂在 net.neoforged:forge 下，版本号带 1.20.1- 前缀
        if mc_version.startswith("1.20.1"):
            return f"{mc_version}-{version}"
        return version
    return version


# ---------------------------------------------------------------- 版本列表

def list_versions(kind: str, mc_version: str) -> list[LoaderVersion]:
    if kind == "fabric":
        return _list_fabric(mc_version)
    if kind == "quilt":
        return _list_quilt(mc_version)
    if kind == "forge":
        return _list_forge(mc_version)
    if kind == "neoforge":
        return _list_neoforge(mc_version)
    raise ValueError(f"未知加载器：{kind}")


def _list_quilt(mc_version: str) -> list[LoaderVersion]:
    """Quilt 的 meta 结构和 Fabric 几乎一样，只是没有 BMCLAPI 镜像。"""
    data = json.loads(_fetch_retry(f"{QUILT_META}/versions/loader/{mc_version}"))
    out: list[LoaderVersion] = []
    for item in data or []:
        loader = item.get("loader") or {}
        ver = str(loader.get("version") or "")
        if not ver:
            continue
        # 带 -beta / -alpha 的是预览版
        stable = not any(t in ver.lower() for t in ("beta", "alpha", "rc", "pre"))
        out.append(LoaderVersion(version=ver, stable=stable))
    out.sort(key=lambda v: _vkey(v.version), reverse=True)
    out.sort(key=lambda v: not v.stable)
    return out


def _list_fabric(mc_version: str) -> list[LoaderVersion]:
    data = None
    for base in (FABRIC_META_BMCL, FABRIC_META_OFFICIAL):
        try:
            data = _get_json(f"{base}/versions/loader/{mc_version}")
            break
        except Exception:                            # noqa: BLE001
            continue
    if not data:
        raise RuntimeError("获取 Fabric 版本列表失败")

    out: list[LoaderVersion] = []
    for item in data:
        loader = item.get("loader") or {}
        out.append(LoaderVersion(
            version=str(loader.get("version") or ""),
            stable=bool(loader.get("stable", True)),
        ))
    # 新的在前；再按稳定性稳定排序，让正式版沉到最上面
    out.sort(key=lambda v: _vkey(v.version), reverse=True)
    out.sort(key=lambda v: not v.stable)
    return [v for v in out if v.version]


def _list_forge(mc_version: str) -> list[LoaderVersion]:
    data = _get_json(f"{BMCLAPI}/forge/minecraft/{mc_version}")
    out = [LoaderVersion(version=str(d.get("version") or "")) for d in data]
    out = [v for v in out if v.version]
    out.sort(key=lambda v: _vkey(v.version), reverse=True)
    return out


def _list_neoforge(mc_version: str) -> list[LoaderVersion]:
    data = _get_json(f"{BMCLAPI}/neoforge/list/{mc_version}")
    out: list[LoaderVersion] = []
    for d in data:
        ver = str(d.get("version") or "")
        if ver.startswith(f"{mc_version}-"):
            ver = ver[len(mc_version) + 1:]
        out.append(LoaderVersion(version=ver))
    out = [v for v in out if v.version]
    out.sort(key=lambda v: _vkey(v.version), reverse=True)
    return out


def _vkey(text: str) -> tuple:
    parts = re.split(r"[.\-+]", text)
    return tuple((0, int(p)) if p.isdigit() else (1, p) for p in parts)


# ---------------------------------------------------------------- Fabric

def _install_fabric(mc_version: str, version: str, game_dir: Path,
                    on_log: Callable[[str], None], cancel) -> str:
    raw = None
    for base in (FABRIC_META_BMCL, FABRIC_META_OFFICIAL):
        try:
            raw = fetch_text(f"{base}/versions/loader/{mc_version}/{version}/profile/json")
            break
        except Exception:                            # noqa: BLE001
            continue
    if not raw:
        raise RuntimeError("获取 Fabric profile 失败")

    profile = json.loads(raw)
    vid = str(profile.get("id") or f"fabric-loader-{version}-{mc_version}")
    folder = Path(game_dir) / "versions" / vid
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{vid}.json").write_text(raw, encoding="utf-8")
    on_log(f"已写入版本文件：versions/{vid}/{vid}.json")

    tasks: list[DownloadTask] = []
    for lib in profile.get("libraries") or []:
        try:
            url, path = _lib_target(lib, "https://maven.fabricmc.net/")
        except ValueError:
            continue
        tasks.append(DownloadTask(url=url, dest=Path(game_dir) / "libraries" / path))

    on_log(f"需要补齐 {len(tasks)} 个库文件")
    dl = Downloader(threads=16)
    if cancel is not None:
        dl.cancelled = cancel if hasattr(cancel, "is_set") else dl.cancelled
    ok, bad = dl.run(tasks, source="bmclapi", on_log=lambda m: on_log(m))
    if bad:
        raise RuntimeError(f"有 {bad} 个库文件下载失败")
    on_log(f"Fabric 安装完成：{vid}")
    return vid


# ---------------------------------------------------------------- Forge / NeoForge

def _installer_urls(kind: str, mc_version: str, version: str) -> list[str]:
    """安装器下载地址候选，快的排前面。"""
    urls: list[str] = []
    if kind == "forge":
        # BMCLAPI 的 /forge/download/<build> 不用走 maven 的 302 跳转链
        try:
            for item in _get_json(f"{BMCLAPI}/forge/minecraft/{mc_version}"):
                if str(item.get("version")) == str(version) and item.get("build"):
                    urls.append(f"{BMCLAPI}/forge/download/{item['build']}")
                    break
        except Exception:                            # noqa: BLE001
            pass
    urls.append(_installer_url(kind, mc_version, version))
    return urls


def _installer_url(kind: str, mc_version: str, version: str) -> str:
    full = full_version(kind, mc_version, version)
    if kind == "forge":
        return f"{FORGE_MIRROR}/net/minecraftforge/forge/{full}/forge-{full}-installer.jar"
    # NeoForge: 1.20.1 走 net.neoforged:forge，之后是 net.neoforged:neoforge
    artifact = "forge" if mc_version.startswith("1.20.1") else "neoforge"
    return f"{FORGE_MIRROR}/net/neoforged/{artifact}/{full}/{artifact}-{full}-installer.jar"


def _run_installer(java: str, jar: Path, game_dir: Path, mirror: str | None,
                   on_log: Callable[[str], None], cancel) -> int:
    cmd = [java, "-jar", str(jar), "--installClient", str(game_dir)]
    if mirror:
        cmd += ["--mirror", mirror]
    on_log("执行：" + " ".join(cmd))
    creation = getattr(subprocess, "CREATE_NO_WINDOW", _CREATE_NO_WINDOW)
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace", cwd=str(game_dir),
        creationflags=creation,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        if cancel is not None and getattr(cancel, "is_set", lambda: False)():
            proc.terminate()
            raise RuntimeError("已取消")
        on_log(line)
    return proc.wait()


def _seed_installer_libs(jar: Path, game_dir: Path,
                         on_log: Callable[[str], None], cancel) -> None:
    """安装器自带的下载器会从 BMCLAPI 拿到坏文件（SHA1 不匹配），还会 302 到黑洞节点。

    所以先把 install_profile 里列出的库按 SHA1 校验补齐；安装器发现文件已经在
    且校验通过，就只跑 processor，不再联网。下载统一走 curl.exe，因为 Python
    的 TLS 会被部分 CDN 掐断。
    """
    import zipfile
    payloads: list[dict] = []
    try:
        with zipfile.ZipFile(jar) as z:
            for name in ("install_profile.json", "version.json"):
                try:
                    payloads.append(json.loads(z.read(name).decode("utf-8")))
                except KeyError:
                    continue
    except (OSError, ValueError) as exc:
        on_log(f"读不到安装器内的元数据：{exc}")
        return
    if not payloads:
        return

    arts: list[tuple[str, Path, str]] = []
    seen: set[str] = set()
    for profile in payloads:
        for lib in profile.get("libraries") or []:
            art = (lib.get("downloads") or {}).get("artifact") or {}
            url, path, sha1 = art.get("url"), art.get("path"), art.get("sha1")
            if not url or not path or path in seen:
                continue
            seen.add(str(path))
            arts.append((str(url), Path(game_dir) / "libraries" / str(path), str(sha1 or "")))
    if not arts:
        return

    on_log(f"预下载安装器依赖：{len(arts)} 个库文件（SHA1 校验，4 线程）")
    stat = {"ok": 0, "skip": 0, "bad": 0, "done": 0}
    lock = threading.Lock()
    total = len(arts)

    def _bump(key: str) -> None:
        with lock:
            stat[key] += 1
            stat["done"] += 1
            done = stat["done"]
        if done == total or done % 5 == 0:
            on_log(f"  进度 {done}/{total}（新下 {stat['ok']}，已存在 {stat['skip']}，失败 {stat['bad']}）")

    def _candidates(url: str, rel: str) -> tuple[str, ...]:
        """按「大概率能通」的顺序排下载地址。

        maven.neoforged.net / maven.minecraftforge.net 在部分网络下握手就超时，
        BMCLAPI 的 /maven/ 有时会被 302 到黑洞节点，而 Maven Central 一般最快。
        所以非 Minecraft 专属的依赖先走 Central，再走 BMCLAPI，最后才是原始地址。
        """
        central = f"https://repo1.maven.org/maven2/{rel}" if rel else ""
        mirror = map_source(url, "bmclapi")
        host = url.split("/")[2].lower() if url.count("/") >= 2 else ""
        mc_only = rel.startswith(("net/minecraftforge/", "net/neoforged/", "de/oceanlabs/",
                                  "cpw/mods/", "net/minecraft/"))
        order: list[str] = []
        if host.endswith("minecraft.net") and "maven" not in host:
            order.append(url)
        if not mc_only and central:
            order.append(central)
        if mirror != url:
            order.append(mirror)
        order.append(url)
        if mc_only and central:
            order.append(central)
        out: list[str] = []
        for item in order:
            if item and item not in out:
                out.append(item)
        return tuple(out)

    def seed_one(item: tuple[str, Path, str]) -> None:
        url, dest, sha1 = item
        if cancel is not None and getattr(cancel, "is_set", lambda: False)():
            return
        if dest.is_file() and (not sha1 or sha1_of(dest) == sha1):
            _bump("skip")
            return
        dest.unlink(missing_ok=True)
        dest.with_suffix(dest.suffix + ".part").unlink(missing_ok=True)
        try:
            rel = dest.relative_to(Path(game_dir) / "libraries").as_posix()
        except ValueError:
            rel = ""
        for candidate in _candidates(url, rel):
            if cancel is not None and getattr(cancel, "is_set", lambda: False)():
                return
            if curl_fetch(candidate, dest, timeout=300, retries=1):
                if not sha1 or sha1_of(dest) == sha1:
                    _bump("ok")
                    return
                dest.unlink(missing_ok=True)
        _bump("bad")
        on_log(f"  下不下来，留给安装器重试：{dest.name}")

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(seed_one, arts))
    on_log(f"依赖就绪：新下 {stat['ok']}，已存在 {stat['skip']}，失败 {stat['bad']}")


def _install_via_installer(kind: str, mc_version: str, version: str, game_dir: Path,
                           java: str, on_log: Callable[[str], None], cancel) -> str:
    game_dir = Path(game_dir)
    game_dir.mkdir(parents=True, exist_ok=True)
    prof = game_dir / "launcher_profiles.json"
    if not prof.is_file():
        prof.write_text(json.dumps({"profiles": {}, "settings": {}, "version": 3}),
                        encoding="utf-8")
        on_log("已创建 launcher_profiles.json（安装器要求）")

    jar = game_dir / f".mclite-{kind}-installer.jar"
    data = b""
    if jar.is_file() and jar.stat().st_size > 0:
        cached = jar.read_bytes()
        if cached.startswith(b"PK"):
            data = cached
            on_log(f"复用上次下载的安装器（{len(data) / 1024 / 1024:.1f} MB）")
    for candidate in ([] if data else _installer_urls(kind, mc_version, version)):
        on_log(f"下载安装器：{candidate}")
        if curl_fetch(candidate, jar, timeout=180) and jar.is_file() and jar.stat().st_size > 0:
            data = jar.read_bytes()
            if data.startswith(b"PK"):
                break
            data = b""
        try:
            data = fetch_bytes_robust(candidate, timeout=90)
            if data.startswith(b"PK"):
                break
        except Exception:                            # noqa: BLE001
            data = b""
    if not data.startswith(b"PK"):
        raise RuntimeError("安装器下载失败（返回的不是 jar 包），请检查网络后重试")
    jar.write_bytes(data)
    on_log(f"安装器已就绪（{len(data) / 1024 / 1024:.1f} MB）")

    versions_dir = game_dir / "versions"
    before = {p.name for p in versions_dir.iterdir()} if versions_dir.is_dir() else set()
    started = time.time()

    rc = 1
    for attempt in (1, 2):
        if cancel is not None and getattr(cancel, "is_set", lambda: False)():
            raise RuntimeError("已取消")
        _seed_installer_libs(jar, game_dir, on_log, cancel)
        on_log(f"第 {attempt} 轮：执行安装器（直连 maven）…")
        rc = _run_installer(java, jar, game_dir, None, on_log, cancel)
        if rc == 0:
            break
        on_log(f"这轮没成功（退出码 {rc}），换镜像再试…")
        rc = _run_installer(java, jar, game_dir, f"{FORGE_MIRROR}/", on_log, cancel)
        if rc == 0:
            break
    if rc != 0:
        raise RuntimeError(f"安装器退出码 {rc}"
                           "（网络不稳定时可以再点一次安装，已下载的文件会复用）")

    vid = _find_installed(kind, mc_version, version, versions_dir, before, started)
    try:
        jar.unlink()
    except OSError:
        pass
    if not vid:
        raise RuntimeError("安装器没有生成版本目录")
    on_log(f"{KINDS[kind]} 安装完成：{vid}")
    return vid


def _find_installed(kind: str, mc_version: str, version: str, versions_dir: Path,
                    before: set[str], started: float) -> str:
    """找出安装器刚写好的版本目录。

    安装器可能复用已存在的同名目录（NeoForge 1.20.x 甚至装成 `1.20.1-forge-47.1.105`
    这种名字，看不出 neoforge），所以先按「名字里带版本号」找，再退回「最新写过的」。
    """
    if not versions_dir.is_dir():
        return ""
    ver_l = version.lower()
    kind_l = kind.lower()
    named: list[str] = []
    fresh: list[str] = []
    for p in versions_dir.iterdir():
        if not p.is_dir():
            continue
        name = p.name.lower()
        if ver_l in name:
            named.append(p.name)
        stamp = 0.0
        for f in p.glob("*.json"):
            try:
                stamp = max(stamp, f.stat().st_mtime)
            except OSError:
                pass
        if stamp >= started - 600:
            fresh.append(p.name)
    if named:
        # 名字里既带加载器名又带版本号的最可信
        best = [n for n in named if kind_l in n.lower() or _KIND_ALIAS.get(kind_l, "") in n.lower()]
        return sorted(best or named)[-1]
    if fresh:
        return sorted(fresh)[-1]
    added = {p.name for p in versions_dir.iterdir()} - before
    return sorted(added)[-1] if added else ""


_KIND_ALIAS = {"neoforge": "forge", "forge": ""}


def _fetch_bytes(url: str, timeout: int = 180) -> bytes:
    import urllib.request

    from .downloader import USER_AGENT
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


# ---------------------------------------------------------------- 对外接口

def install(kind: str, mc_version: str, version: str, game_dir: Path, java: str,
            on_log: Callable[[str], None] = lambda _m: None,
            cancel=None) -> str:
    """安装加载器，返回装好后的版本 id。"""
    if kind == "fabric":
        return _install_fabric(mc_version, version, Path(game_dir), on_log, cancel)
    if kind == "quilt":
        return _install_quilt(mc_version, version, Path(game_dir), on_log, cancel)
    if kind in ("forge", "neoforge"):
        return _install_via_installer(kind, mc_version, version, Path(game_dir),
                                      java, on_log, cancel)
    raise ValueError(f"未知加载器：{kind}")


def _install_quilt(mc_version: str, version: str, game_dir: Path,
                   on_log: Callable[[str], None], cancel) -> str:
    """Quilt：和 Fabric 同构，官方 meta 直接给 profile JSON。

    整合包市场里有相当一部分包是 Quilt 的（例如 Sodium Plus），
    以前会在这里报「未知加载器：quilt」。
    """
    raw = _fetch_retry(f"{QUILT_META}/versions/loader/{mc_version}/{version}/profile/json")
    profile = json.loads(raw)
    vid = str(profile.get("id") or f"quilt-loader-{version}-{mc_version}")
    folder = Path(game_dir) / "versions" / vid
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{vid}.json").write_text(raw, encoding="utf-8")
    on_log(f"已写入版本文件：versions/{vid}/{vid}.json")

    tasks: list[DownloadTask] = []
    for lib in profile.get("libraries") or []:
        try:
            url, path = _lib_target(lib, "https://maven.quiltmc.org/repository/release/")
        except ValueError:
            continue
        tasks.append(DownloadTask(url=url, dest=Path(game_dir) / "libraries" / path))

    on_log(f"需要补齐 {len(tasks)} 个库文件")
    # 上次失败可能留下半截 .part，断点续传会读到坏数据，先清掉
    for t in tasks:
        part = t.dest.with_suffix(t.dest.suffix + ".part")
        if part.is_file():
            try:
                part.unlink()
            except OSError:
                pass
    dl = Downloader(threads=16)
    if cancel is not None:
        dl.cancelled = cancel if hasattr(cancel, "is_set") else dl.cancelled
    # 这些库的 maven 是 maven.fabricmc.net，官方源经常 60 秒只吐一半，
    # 走 BMCLAPI 的 /maven/ 代理（302 到中科大，1.5 秒下完），失败的再回落官方。
    ok, bad = dl.run(tasks, source="bmclapi", on_log=lambda m: on_log(m))

    # 官方 maven 的 TLS 对 Python 很不友好，失败的用 curl.exe 补一遍
    if bad:
        retry = [t for t in tasks if not t.ok]
        on_log(f"{len(retry)} 个库文件用 curl 重试")
        fixed = 0
        for t in retry:
            if cancel is not None and getattr(cancel, "is_set", None) and cancel.is_set():
                break
            if curl_fetch(t.url, t.dest, timeout=120, on_log=None):
                t.ok = True
                fixed += 1
        bad -= fixed
        if fixed:
            on_log(f"curl 补下成功 {fixed} 个")
    if bad:
        raise RuntimeError(f"有 {bad} 个库文件下载失败")
    on_log(f"Quilt 安装完成：{vid}")
    return vid


def installed_loader_versions(game_dir: Path) -> list[str]:
    """挑出已装好的加载器版本目录名，供 UI 提示用。"""
    d = Path(game_dir) / "versions"
    if not d.is_dir():
        return []
    out = []
    for p in d.iterdir():
        if not p.is_dir():
            continue
        name = p.name.lower()
        if "forge" in name or "fabric" in name or "quilt" in name or "neoforge" in name:
            out.append(p.name)
    return sorted(out)


def loader_complete(game_dir: Path, vid: str) -> bool:
    """加载器是否真的装全了（版本文件在、库文件也齐）。

    只按目录名判「已装」会出问题：上一次装到一半失败时 ``versions/<vid>``
    已经建好，下次就会直接跳过，留下一个所有库都缺的坏实例。
    """
    game_dir = Path(game_dir)
    vdir = game_dir / "versions" / vid
    vjson = vdir / f"{vid}.json"
    if not vjson.is_file():
        return False
    try:
        data = json.loads(vjson.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return False
    libs = data.get("libraries") or []
    if not isinstance(libs, list):
        return False
    try:
        from .versionmeta import rules_allow
    except Exception:                                # noqa: BLE001
        rules_allow = lambda _r, _f=None: True       # noqa: E731
    for lib in libs:
        if not isinstance(lib, dict):
            continue
        # natives 之类不需要本地文件，跳过
        if lib.get("natives"):
            continue
        # 别的平台（linux/macos）的库本来就不该下，别算成缺失
        if not rules_allow(lib.get("rules")):
            continue
        try:
            _url, path = _lib_target(lib, "")
        except (ValueError, KeyError):
            continue
        if not (game_dir / "libraries" / path).is_file():
            return False
    return True
