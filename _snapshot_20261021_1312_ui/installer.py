"""安装器：下载并安装一个版本的 client.jar、libraries、assets、版本 JSON。"""

from __future__ import annotations

import json
import os
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .downloader import (
    DownloadTask,
    Downloader,
    Progress,
    fetch_json,
    fetch_text,
    human_size,
)
from .versionmeta import (
    ASSETS_URL,
    VersionSummary,
    asset_index_of,
    build_asset_tasks,
    resolve_libraries,
)

ProgressCb = Callable[[Progress], None]
LogCb = Callable[[str], None]


@dataclass
class InstallPlan:
    version_id: str
    version_json: dict[str, Any]
    tasks: list[DownloadTask] = field(default_factory=list)
    libraries: list = field(default_factory=list)
    total_bytes: int = 0

    def summary(self) -> str:
        libs = len(self.libraries)
        return f"版本 {self.version_id}：{len(self.tasks)} 个文件，{libs} 个库，{human_size(self.total_bytes)}"


class Installer:
    def __init__(
        self,
        game_dir: Path,
        source: str = "official",
        threads: int = 16,
        log: LogCb | None = None,
    ) -> None:
        self.game_dir = Path(game_dir)
        self.source = source
        self.threads = threads
        self.log = log or (lambda _m: None)
        self.downloader = Downloader(threads=threads)
        self.cancelled = self.downloader.cancelled
        self.version_json: dict[str, Any] = {}
        self.version_id = ""

    # ------------------------------------------------------------ 路径

    @property
    def versions_dir(self) -> Path:
        return self.game_dir / "versions"

    @property
    def libraries_dir(self) -> Path:
        return self.game_dir / "libraries"

    @property
    def assets_dir(self) -> Path:
        return self.game_dir / "assets"

    # ------------------------------------------------------------ 取元数据

    def fetch_version_json(self, url: str) -> dict[str, Any]:
        self.log("正在获取版本元数据…")
        return fetch_json(url, source=self.source)

    def fetch_version_raw(self, url: str) -> tuple[dict[str, Any], str]:
        """返回 (解析后的 JSON, 原始文本)，原始文本用于原样落盘。"""
        self.log("正在获取版本元数据…")
        text = fetch_text(url, source=self.source)
        return json.loads(text), text

    def fetch_assets_index(self, index_url: str) -> dict[str, Any]:
        self.log("正在获取资源索引…")
        return fetch_json(index_url, source=self.source)

    # ------------------------------------------------------------ 规划

    def plan(self, version_id: str, version_json: dict[str, Any],
             raw_text: str | None = None) -> InstallPlan:
        self.version_id = version_id
        self.version_json = version_json
        plan = InstallPlan(version_id=version_id, version_json=version_json)

        vid = version_json.get("id") or version_id
        vdir = self.versions_dir / version_id
        vdir.mkdir(parents=True, exist_ok=True)

        # 1) 版本 JSON 落盘：优先原样写入，避免重新序列化带来的差异
        json_path = vdir / f"{version_id}.json"
        text = raw_text if raw_text is not None else json.dumps(
            version_json, ensure_ascii=False, indent=2)
        try:
            json_path.write_text(text, encoding="utf-8")
        except OSError:
            pass

        # 2) client.jar
        client = (version_json.get("downloads") or {}).get("client") or {}
        if client.get("url"):
            plan.tasks.append(DownloadTask(
                url=client["url"],
                dest=vdir / f"{vid}.jar",
                sha1=client.get("sha1"),
                size=client.get("size"),
            ))

        # 3) libraries
        libs = resolve_libraries(version_json)
        plan.libraries = libs
        for lib in libs:
            if not lib.url or not lib.sha1:
                # 无 URL 的库：本地已存在就跳过，否则记一条占位（forge 安装器会补齐）
                continue
            plan.tasks.append(DownloadTask(
                url=lib.url,
                dest=self.libraries_dir / Path(lib.path),
                sha1=lib.sha1,
                size=lib.size,
            ))

        # 4) assets 索引在 install 阶段单独获取并原样落盘，这里不计入下载任务
        plan.total_bytes = sum(t.size or 0 for t in plan.tasks)
        # 资源体积未知，给个经验估算
        plan.total_bytes += 220 * 1024 * 1024
        return plan

    # ------------------------------------------------------------ 执行

    def install(
        self,
        version_id: str,
        url: str,
        progress_cb: ProgressCb | None = None,
    ) -> tuple[bool, str]:
        try:
            vjson, raw = self.fetch_version_raw(url)
        except Exception as exc:                       # noqa: BLE001
            return False, f"获取版本元数据失败：{exc}"

        plan = self.plan(version_id, vjson, raw)
        self.log(plan.summary())

        ok, bad = self.downloader.run(
            plan.tasks,
            source=self.source,
            progress_cb=progress_cb,
            on_log=self.log,
        )
        if bad:
            if self.cancelled.is_set():
                return False, "用户取消"
            return False, f"{bad} 个文件下载失败"

        # assets 展开
        idx = asset_index_of(vjson)
        if idx and idx.url:
            try:
                index_text = fetch_text(idx.url, source=self.source)
                index_json = json.loads(index_text)
            except Exception as exc:                   # noqa: BLE001
                return False, f"获取资源索引失败：{exc}"
            index_path = self.assets_dir / "indexes" / f"{idx.id}.json"
            try:
                index_path.parent.mkdir(parents=True, exist_ok=True)
                index_path.write_text(index_text, encoding="utf-8")
            except OSError:
                pass

            asset_tasks = build_asset_tasks(index_json, self.assets_dir)
            self.log(f"资源文件 {len(asset_tasks)} 个")
            ok2, bad2 = self.downloader.run(
                asset_tasks,
                source=self.source,
                progress_cb=progress_cb,
                on_log=self.log,
            )
            if bad2:
                if self.cancelled.is_set():
                    return False, "用户取消"
                return False, f"{bad2} 个资源文件下载失败"

        # 校验 jar
        jar = self.versions_dir / version_id / f"{vjson.get('id') or version_id}.jar"
        if not jar.is_file():
            return False, "client.jar 缺失"

        self.log("安装完成")
        return True, "安装成功"

    # ------------------------------------------------------------ 杂项

    def extract_natives(self, version_id: str, natives_dir: Path) -> None:
        """把带 natives 的库解压到版本目录下的 natives 文件夹。"""
        vjson = self.version_json or {}
        natives_dir.mkdir(parents=True, exist_ok=True)
        for lib in resolve_libraries(vjson):
            if not lib.is_native:
                continue
            jar = self.libraries_dir / Path(lib.path)
            if not jar.is_file():
                continue
            self._extract_jar(jar, natives_dir, lib.extract_exclude)

    @staticmethod
    def _extract_jar(jar: Path, dest: Path, exclude: list[str] | None) -> None:
        exclude = exclude or ["META-INF/"]
        try:
            with zipfile.ZipFile(jar) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    name = info.filename
                    if any(name.startswith(p) for p in exclude):
                        continue
                    target = dest / name
                    try:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(info) as src, open(target, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                    except OSError:
                        continue
        except (OSError, zipfile.BadZipFile):
            pass


def remove_version(game_dir: Path, version_id: str) -> bool:
    """删除一个版本目录。"""
    vdir = Path(game_dir) / "versions" / version_id
    if not vdir.is_dir():
        return False
    try:
        shutil.rmtree(vdir, ignore_errors=False)
        return True
    except OSError:
        return False
