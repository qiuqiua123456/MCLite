"""CurseForge 整合包的模组自动下载（不需要 API Key）。

CurseForge 官方 API 要 Key，而且本机连它全被 403。绕路办法：

1. ``https://api.cfwidget.com/{projectID}`` 是第三方只读镜像，返回里 ``files[]``
   带每个文件的 ``id`` 与 ``name``（就是 jar 文件名）；
2. 拿到 ``(fileID, 文件名)`` 之后，CDN 直链是可拼的：
   ``https://edge.forgecdn.net/files/{id // 1000}/{id % 1000}/{文件名}``
   （会 302 到 ``mediafilez.forgecdn.net``，两个都可用）；
3. 所以 manifest.json 里的 ``projectID + fileID`` 足够定位到文件。

本机 Python 的 TLS 容易被掐，所以这里的 JSON 用 ``curl.exe`` 拿。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .downloader import DownloadTask, Downloader, human_size

CFWIDGET = "https://api.cfwidget.com/{project}"
CF_PROJECT_PAGE = "https://www.curseforge.com/projects/{project}"

#: 兜底用的第二个 CDN（edge 会 302 到它）
CDN_HOSTS = ("https://edge.forgecdn.net", "https://mediafilez.forgecdn.net")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

_CURL = shutil.which("curl") or r"C:\Windows\System32\curl.exe"

#: projectID -> {fileID: 文件名}
_cache: dict[int, dict[int, str]] = {}
#: projectID -> 失败原因（别对着同一个坏项目反复等超时）
_failed: dict[int, str] = {}


class CurseForgeError(Exception):
    """拿不到 CurseForge 元数据时抛出。"""


# ---------------------------------------------------------------- CDN 直链

def cdn_urls(file_id: int, name: str) -> list[str]:
    """按 CurseForge 的目录规则拼出 CDN 直链（含备用 CDN）。"""
    tail = f"files/{file_id // 1000}/{file_id % 1000}/{urllib.parse.quote(name)}"
    return [f"{host}/{tail}" for host in CDN_HOSTS]


def project_page(project_id: int) -> str:
    return CF_PROJECT_PAGE.format(project=project_id)


# ---------------------------------------------------------------- 元数据

def _curl_json(url: str, timeout: int = 40) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="mclite-cf-")) / "r.json"
    cmd = [_CURL, "-sSL", "--compressed", "--max-time", str(timeout),
           "--retry", "1", "--retry-delay", "2", "-A", UA, "-o", str(tmp), url]
    try:
        proc = subprocess.run(cmd, capture_output=True,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if proc.returncode != 0:
            raise CurseForgeError(f"curl 失败（rc={proc.returncode}）")
        if not tmp.exists() or tmp.stat().st_size < 16:
            raise CurseForgeError("返回内容为空")
        text = tmp.read_text("utf-8", "replace")
    finally:
        shutil.rmtree(tmp.parent, ignore_errors=True)
    try:
        return json.loads(text)
    except ValueError as exc:
        raise CurseForgeError(f"返回不是 JSON（{exc}）") from exc


def project_files(project_id: int, timeout: int = 25) -> dict[int, str]:
    """projectID → {fileID: 文件名}，带进程内缓存（成功与失败都缓存）。"""
    key = int(project_id)
    if key in _cache:
        return _cache[key]
    if key in _failed:
        raise CurseForgeError(_failed[key])
    try:
        data = _curl_json(CFWIDGET.format(project=key), timeout=timeout)
    except CurseForgeError as exc:
        _failed[key] = str(exc)
        raise
    mapping: dict[int, str] = {}
    for item in data.get("files") or []:
        fid, name = item.get("id"), item.get("name") or ""
        if isinstance(fid, int) and name.lower().endswith((".jar", ".zip")):
            mapping[fid] = name
    download = data.get("download") or {}
    if isinstance(download.get("id"), int) and download.get("name"):
        mapping.setdefault(int(download["id"]), str(download["name"]))
    if not mapping:
        _failed[key] = "这个项目没返回文件列表"
        raise CurseForgeError(_failed[key])
    _cache[key] = mapping
    return mapping


def file_name(project_id: int, file_id: int, timeout: int = 25) -> str:
    """查某个文件的 jar 文件名，查不到返回空串。"""
    return project_files(project_id, timeout=timeout).get(int(file_id), "")


# ---------------------------------------------------------------- 解析

def resolve(files: list[dict], on_log=lambda _m: None,
            threads: int = 6, timeout: int = 25) -> tuple[list[dict], list[dict]]:
    """把 manifest 里的 ``files[]`` 解析成可下载项。

    返回 ``(可下载列表, 缺失列表)``；可下载项含 ``url`` / ``name`` / ``project`` / ``file``。
    """
    items: list[dict] = []
    missing: list[dict] = []
    total = len(files)
    done = 0
    projects = sorted({int(f["projectID"]) for f in files if f.get("projectID")})
    on_log(f"CurseForge 模组：{total} 个文件，涉及 {len(projects)} 个项目；先查下载地址…")

    def work(entry: dict) -> dict | None:
        pid, fid = int(entry["projectID"]), int(entry["fileID"])
        try:
            name = file_name(pid, fid, timeout=timeout)
        except CurseForgeError as exc:
            return {"project": pid, "file": fid, "reason": str(exc)}
        if not name:
            return {"project": pid, "file": fid, "reason": "文件列表里没有这个 fileID"}
        return {"project": pid, "file": fid, "name": name,
                "urls": cdn_urls(fid, name), "required": bool(entry.get("required", True))}

    with ThreadPoolExecutor(max_workers=max(1, threads)) as pool:
        for result in pool.map(work, files):
            done += 1
            if result and "urls" in result:
                items.append(result)
            elif result:
                missing.append(result)
    on_log(f"地址解析完成：可用 {len(items)} 个，缺失 {len(missing)} 个")
    return items, missing


# ---------------------------------------------------------------- 下载

def download_mods(items: list[dict], mods_dir: Path, on_log=lambda _m: None,
                  progress_cb=None, cancel=None, threads: int = 6) -> tuple[int, list[dict]]:
    """把解析好的模组下到 ``mods_dir``，返回 ``(成功数, 失败列表)``。"""
    mods_dir.mkdir(parents=True, exist_ok=True)
    tasks: list[DownloadTask] = []
    index: dict[str, dict] = {}
    for item in items:
        dest = mods_dir / item["name"]
        if dest.is_file() and dest.stat().st_size > 0:
            continue                                     # 已有同名文件就跳过
        urls = item.get("urls") or []
        if not urls:
            continue
        tasks.append(DownloadTask(urls[0], dest))
        index[str(dest)] = item
    if not tasks:
        on_log("模组文件都已存在，无需下载")
        return 0, []
    on_log(f"开始下载 {len(tasks)} 个模组…")
    ok, bad = Downloader(threads=threads, timeout=60, retries=2).run(
        tasks, progress_cb=progress_cb, on_log=on_log)
    failed: list[dict] = []
    for task in tasks:
        if not task.dest.is_file() or task.dest.stat().st_size == 0:
            failed.append(index.get(str(task.dest), {}))
    on_log(f"模组下载完成：成功 {ok}，失败 {len(failed)}")
    return ok, failed


def describe_missing(missing: list[dict], limit: int = 6) -> str:
    """缺失项拼成一句人话，附上项目页地址。"""
    if not missing:
        return ""
    parts = []
    for item in missing[:limit]:
        parts.append(f"项目 {item.get('project')}（{item.get('reason', '未知原因')}）")
    text = "；".join(parts)
    if len(missing) > limit:
        text += f" 等 {len(missing)} 个"
    text += "。可在浏览器打开 https://www.curseforge.com/projects/<项目号> 手动下载"
    return text


def install(files: list[dict], mods_dir: Path, on_log=lambda _m: None,
            progress_cb=None, cancel=None) -> tuple[int, list[dict]]:
    """一步到位：解析 + 下载。"""
    items, missing = resolve(files, on_log=on_log)
    if cancel is not None and cancel():
        return 0, missing
    ok, failed = download_mods(items, mods_dir, on_log=on_log,
                               progress_cb=progress_cb, cancel=cancel)
    return ok, missing + [item for item in failed if item]


def summary(ok: int, missing: list[dict]) -> str:
    """给日志用的一行总结。"""
    text = f"已自动下载 {ok} 个模组"
    if missing:
        text += f"，{len(missing)} 个需要手动补"
    return text


def size_hint(bytes_total: int) -> str:
    return human_size(bytes_total)
