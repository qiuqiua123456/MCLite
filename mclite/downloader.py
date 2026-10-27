"""下载器：多线程、镜像替换、SHA1 校验、断点续传与进度回调。

设计要点：
    * 只用标准库（urllib），避免额外依赖；
    * 下载源可在官方 <-> BMCLAPI 之间切换，按 URL 前缀映射；
    * 每个任务有 (已完成字节, 总字节)，用一个聚合器汇总成 0~1 的进度；
    * 线程数可配，默认 16，够用又不会把家用带宽打满。
"""

from __future__ import annotations

import hashlib
import os
import queue
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

USER_AGENT = "MCLite/1.0 (+https://localhost)"

# ---------------------------------------------------------------- 镜像映射

# 官方源 -> BMCLAPI 源
MIRROR_PREFIXES: list[tuple[str, str]] = [
    ("https://launchermeta.mojang.com", "https://bmclapi2.bangbang93.com"),
    ("https://piston-meta.mojang.com", "https://bmclapi2.bangbang93.com"),
    ("https://piston-data.mojang.com", "https://bmclapi2.bangbang93.com"),
    ("https://launcher.mojang.com", "https://bmclapi2.bangbang93.com"),
    ("https://libraries.minecraft.net", "https://bmclapi2.bangbang93.com/maven"),
    ("https://resources.download.minecraft.net", "https://bmclapi2.bangbang93.com/assets"),
    # 各加载器的 maven：BMCLAPI 会把 /maven/<path> 代理回原站
    ("https://maven.minecraftforge.net", "https://bmclapi2.bangbang93.com/maven"),
    ("https://files.minecraftforge.net/maven", "https://bmclapi2.bangbang93.com/maven"),
    ("https://maven.neoforged.net/releases", "https://bmclapi2.bangbang93.com/maven"),
    ("https://maven.fabricmc.net", "https://bmclapi2.bangbang93.com/maven"),
    ("https://maven.quiltmc.org/repository/release", "https://bmclapi2.bangbang93.com/maven"),
]


def map_source(url: str, source: str) -> str:
    """按下载源偏好改写 URL。官方源失败时会由调用方回退。"""
    if source != "bmclapi":
        return url
    for official, mirror in MIRROR_PREFIXES:
        if url.startswith(official):
            rest = url[len(official):]
            return mirror + rest
    return url


# ---------------------------------------------------------------- 数据结构

@dataclass
class DownloadTask:
    url: str
    dest: Path
    sha1: str | None = None
    size: int | None = None
    # 运行时状态
    done: int = 0
    total: int = 0
    ok: bool = False
    error: str = ""

    @property
    def name(self) -> str:
        return self.dest.name


@dataclass
class Progress:
    """线程安全的进度聚合器。"""

    total_bytes: int = 0
    done_bytes: int = 0
    total_files: int = 0
    done_files: int = 0
    failed_files: int = 0
    speed: float = 0.0
    current: str = ""
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _last_t: float = field(default=0.0, repr=False)
    _last_b: int = field(default=0, repr=False)

    def add_file(self, size: int) -> None:
        with self._lock:
            self.total_files += 1
            self.total_bytes += max(0, size)

    def add_bytes(self, n: int, name: str = "") -> None:
        with self._lock:
            self.done_bytes += n
            if name:
                self.current = name
            now = time.time()
            if now - self._last_t >= 0.4:
                dt = now - self._last_t
                if dt > 0:
                    self.speed = (self.done_bytes - self._last_b) / dt
                self._last_t = now
                self._last_b = self.done_bytes

    def finish_file(self, ok: bool) -> None:
        with self._lock:
            if ok:
                self.done_files += 1
            else:
                self.failed_files += 1

    def percent(self) -> float:
        with self._lock:
            if self.total_bytes > 0:
                return min(1.0, self.done_bytes / self.total_bytes)
            if self.total_files > 0:
                return min(1.0, self.done_files / self.total_files)
            return 0.0

    def snapshot(self) -> tuple[float, str, float]:
        with self._lock:
            pct = 0.0
            if self.total_bytes > 0:
                pct = min(1.0, self.done_bytes / self.total_bytes)
            elif self.total_files > 0:
                pct = min(1.0, self.done_files / self.total_files)
            return pct, self.current, self.speed


# ---------------------------------------------------------------- 工具函数

def sha1_of(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} GB"


def human_speed(n: float) -> str:
    return human_size(n) + "/s"


# ---------------------------------------------------------------- curl 兜底

CURL = shutil.which("curl") or r"C:\Windows\System32\curl.exe"


def curl_fetch(url: str, dest: Path, timeout: int = 120, retries: int = 3,
               on_log: Callable[[str], None] | None = None) -> bool:
    """用系统自带 curl.exe 下载。

    某些 CDN（Cloudflare 后的 maven.minecraftforge.net、BMCLAPI 的 /maven/）
    会掐掉 Python 的 TLS 连接：握手能成，读数据一直超时，而 curl 3 秒就下完。
    所以这里留一条不依赖 Python 网络栈的退路。
    """
    if not CURL or not Path(CURL).exists():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    cmd = [CURL, "-fLsS", "--retry", str(retries), "--retry-delay", "2",
           "--retry-all-errors", "--connect-timeout", "15",
           "--speed-limit", "1024", "--speed-time", "25",
           "--max-time", str(timeout), "-A", USER_AGENT, "-o", str(tmp), url]
    try:
        rc = subprocess.run(cmd, capture_output=True, text=True,
                            creationflags=_CREATE_NO_WINDOW).returncode
    except OSError:
        return False
    if rc != 0 or not tmp.is_file() or tmp.stat().st_size == 0:
        tmp.unlink(missing_ok=True)
        if on_log:
            on_log(f"curl 下载失败（rc={rc}）：{url}")
        return False
    tmp.replace(dest)
    return True


def fetch_bytes_robust(url: str, timeout: int = 60, attempts: int = 2) -> bytes:
    """先试 urllib，失败再交给 curl.exe 落地到临时文件读回来。"""
    last: Exception | None = None
    for _ in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as exc:                     # noqa: BLE001
            last = exc
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "blob"
        if curl_fetch(url, tmp, timeout=timeout):
            return tmp.read_bytes()
    raise last or RuntimeError(f"下载失败：{url}")


# ---------------------------------------------------------------- 下载实现

class Downloader:
    """批量下载器。

    tasks 里已存在且 SHA1 匹配的文件会被直接跳过（秒装）。
    """

    def __init__(self, threads: int = 16, timeout: int = 30, retries: int = 3) -> None:
        self.threads = max(1, min(64, threads))
        self.timeout = timeout
        self.retries = retries
        self.cancelled = threading.Event()

    # ---------------------------------------------------------- 单文件

    def _fetch_one(self, task: DownloadTask, progress: Progress, source: str) -> None:
        if self.cancelled.is_set():
            task.error = "已取消"
            return

        dest = task.dest
        # 已存在且校验通过 -> 跳过
        if dest.is_file():
            if task.sha1:
                try:
                    if sha1_of(dest) == task.sha1:
                        size = dest.stat().st_size
                        task.done = size
                        task.total = size
                        task.ok = True
                        progress.add_bytes(size, "")
                        progress.finish_file(True)
                        return
                except OSError:
                    pass
            elif task.size and dest.stat().st_size == task.size:
                task.done = task.size
                task.total = task.size
                task.ok = True
                progress.add_bytes(task.size, "")
                progress.finish_file(True)
                return

        dest.parent.mkdir(parents=True, exist_ok=True)
        urls = [map_source(task.url, source)]
        if source != "official":
            # 镜像失败时回退官方
            urls.append(task.url)
        elif task.url.startswith(("https://launchermeta", "https://piston", "https://libraries")):
            # 官方失败时回退镜像
            urls.append(map_source(task.url, "bmclapi"))

        last_err = ""
        for attempt in range(self.retries):
            for url in urls:
                if self.cancelled.is_set():
                    task.error = "已取消"
                    return
                try:
                    self._download_to(url, dest, task, progress)
                    task.ok = True
                    progress.finish_file(True)
                    return
                except Exception as exc:            # noqa: BLE001 - 需要吞掉各类网络异常
                    last_err = f"{type(exc).__name__}: {exc}"
                    continue
            time.sleep(0.6 * (attempt + 1))

        task.error = last_err or "未知错误"
        progress.finish_file(False)

    def _download_to(self, url: str, dest: Path, task: DownloadTask, progress: Progress) -> None:
        tmp = dest.with_suffix(dest.suffix + ".part")
        h = hashlib.sha1()
        got = 0
        mode = "wb"

        # 断点续传：.part 已有内容就带 Range 续上（服务器不支持则重下）
        if tmp.is_file():
            try:
                have = tmp.stat().st_size
                if have > 0:
                    with open(tmp, "rb") as fh:
                        for chunk in iter(lambda: fh.read(1 << 20), b""):
                            h.update(chunk)
                    got = have
                    mode = "ab"
                    progress.add_bytes(have, task.name)
            except OSError:
                got = 0
                mode = "wb"

        headers = {"User-Agent": USER_AGENT}
        if got > 0:
            headers["Range"] = f"bytes={got}-"

        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            if got > 0 and resp.status != 206:
                # 服务器不认 Range，只能从头来
                h = hashlib.sha1()
                got = 0
                mode = "wb"
            total = int(resp.headers.get("Content-Length") or 0) + got
            task.total = total or (task.size or 0)
            with open(tmp, mode) as fh:
                while True:
                    if self.cancelled.is_set():
                        raise RuntimeError("已取消")
                    chunk = resp.read(1 << 16)
                    if not chunk:
                        break
                    fh.write(chunk)
                    h.update(chunk)
                    got += len(chunk)
                    task.done = got
                    progress.add_bytes(len(chunk), task.name)
        if task.sha1 and h.hexdigest().lower() != task.sha1.lower():
            try:
                tmp.unlink()
            except OSError:
                pass
            raise ValueError(f"SHA1 校验失败：期望 {task.sha1[:12]}… 实际 {h.hexdigest()[:12]}…")
        os.replace(tmp, dest)
        task.done = task.total = got

    # ---------------------------------------------------------- 批量

    def run(
        self,
        tasks: Iterable[DownloadTask],
        source: str = "official",
        progress_cb: Callable[[Progress], None] | None = None,
        on_log: Callable[[str], None] | None = None,
    ) -> tuple[int, int]:
        """执行下载，返回 (成功数, 失败数)。"""
        task_list = [t for t in tasks]
        progress = Progress()
        for t in task_list:
            progress.add_file(t.size or 0)

        # 先做一次快速跳过统计，避免进度条从 0 慢慢爬
        pending: list[DownloadTask] = []
        for t in task_list:
            if self._already_ok(t):
                t.ok = True
                progress.add_bytes(t.done, "")
                progress.finish_file(True)
            else:
                pending.append(t)

        if on_log:
            on_log(f"共 {len(task_list)} 个文件，其中 {len(task_list) - len(pending)} 个已存在，"
                   f"需要下载 {len(pending)} 个")

        if not pending:
            return len(task_list), 0

        q: queue.Queue[DownloadTask] = queue.Queue()
        for t in pending:
            q.put(t)

        def worker() -> None:
            while True:
                if self.cancelled.is_set():
                    return
                try:
                    t = q.get_nowait()
                except queue.Empty:
                    return
                try:
                    self._fetch_one(t, progress, source)
                finally:
                    q.task_done()

        n = min(self.threads, max(1, len(pending)))
        workers = [threading.Thread(target=worker, daemon=True) for _ in range(n)]
        for w in workers:
            w.start()

        while any(w.is_alive() for w in workers):
            if progress_cb:
                try:
                    progress_cb(progress)
                except Exception:                    # noqa: BLE001
                    pass
            time.sleep(0.15)
        for w in workers:
            w.join(timeout=2)
        if progress_cb:
            try:
                progress_cb(progress)
            except Exception:                        # noqa: BLE001
                pass

        ok = sum(1 for t in task_list if t.ok)
        bad = len(task_list) - ok
        if on_log and bad:
            for t in task_list:
                if not t.ok:
                    on_log(f"下载失败：{t.dest.name}  {t.error}")
        return ok, bad

    def _already_ok(self, t: DownloadTask) -> bool:
        if not t.dest.is_file():
            return False
        try:
            if t.sha1:
                ok = sha1_of(t.dest) == t.sha1.lower()
            elif t.size:
                ok = t.dest.stat().st_size == t.size
            else:
                ok = t.dest.stat().st_size > 0
            if ok:
                t.done = t.total = t.dest.stat().st_size
            return ok
        except OSError:
            return False


# ---------------------------------------------------------------- 轻量请求

def fetch_text(url: str, timeout: int = 25, source: str = "official") -> str:
    """取文本（JSON），官方失败自动回退镜像。"""
    urls = [map_source(url, source)]
    if source != "official":
        urls.append(url)
    last: Exception | None = None
    for u in urls:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception as exc:                     # noqa: BLE001
            last = exc
    raise RuntimeError(f"请求失败：{url}（{last}）")


def fetch_json(url: str, timeout: int = 25, source: str = "official"):
    import json
    return json.loads(fetch_text(url, timeout=timeout, source=source))
