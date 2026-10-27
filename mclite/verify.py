"""校验 / 补全游戏文件：找出缺失的客户端 jar、库、资源索引与资源文件，并补齐。

检查阶段只做「存在性」判断，不联网、不计算 SHA1，因此 1.20.1（约 3600 项）
通常半秒内就能跑完；真正补全时再交给 :class:`~mclite.downloader.Downloader`
去下载并做 SHA1 校验。

用法::

    from mclite.verify import check, repair

    report = check(game_dir, "1.20.1")
    print(report.summary())
    if not report.ok:
        ok, msg = repair(game_dir, "1.20.1", on_log=print)
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .downloader import DownloadTask, Downloader, Progress, fetch_text
from .launcher import GameLauncher, LaunchError
from .versionmeta import (
    ASSETS_URL,
    asset_index_of,
    asset_objects,
    resolve_libraries,
)

#: summary 里分类统计的顺序，以及各分类的中文名
_KIND_ORDER = ("jar", "library", "index", "asset")
_KIND_LABELS = {
    "jar": "客户端 jar",
    "library": "库",
    "index": "资源索引",
    "asset": "资源",
}


@dataclass
class MissingItem:
    kind: str        # "jar" | "library" | "asset" | "index"
    name: str        # 人类可读，如 "客户端 jar"、"net.fabricmc:loader:0.19.5"
    path: Path
    url: str = ""
    sha1: str = ""
    size: int = 0


@dataclass
class CheckReport:
    version_id: str
    jar_ok: bool
    checked: int
    missing: list[MissingItem]

    @property
    def ok(self) -> bool:
        return not self.missing

    def summary(self) -> str:
        if not self.missing:
            return f"{self.version_id}：检查 {self.checked} 项，文件完整"
        counts: dict[str, int] = {}
        for item in self.missing:
            counts[item.kind] = counts.get(item.kind, 0) + 1
        parts = [
            f"{_KIND_LABELS.get(kind, kind)} {counts[kind]}"
            for kind in _KIND_ORDER
            if kind in counts
        ]
        for kind, n in counts.items():
            if kind not in _KIND_ORDER:
                parts.append(f"{kind} {n}")
        detail = f"（{'、'.join(parts)}）" if parts else ""
        return f"{self.version_id}：检查 {self.checked} 项，缺失 {len(self.missing)} 项{detail}"


# ---------------------------------------------------------------- 内部工具

def _cancelled(cancel: threading.Event | None) -> bool:
    return cancel is not None and cancel.is_set()


def _jar_path(launcher: GameLauncher, version_id: str,
              vjson: dict[str, Any]) -> tuple[Path, bool]:
    """返回 (客户端 jar 路径, 是否存在)。

    继承版本（Forge / Fabric / NeoForge）的 jar 在父版本目录里，不要求
    自身目录下有 jar；找不到时按 ``_jar_from`` 推算一个下载落点。
    """
    try:
        return launcher.version_jar(version_id, vjson), True
    except LaunchError:
        pass
    src = str(vjson.get("_jar_from") or vjson.get("jar") or "")
    if src and src != version_id:
        return launcher.versions_dir / src / f"{src}.jar", False
    vid = str(vjson.get("id") or version_id)
    return launcher.versions_dir / version_id / f"{vid}.jar", False


def _read_index(path: Path) -> dict[str, Any] | None:
    """读取资源索引；文件缺失、为空或内容损坏时返回 None。"""
    try:
        if not path.is_file() or path.stat().st_size <= 0:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


# ---------------------------------------------------------------- 检查

def check(game_dir: Path, version_id: str) -> CheckReport:
    """检查一个版本的文件完整性，返回缺失清单（不联网）。

    版本 JSON 缺失或继承链断裂时抛 :class:`~mclite.launcher.LaunchError`。
    """
    game_dir = Path(game_dir)
    launcher = GameLauncher(game_dir)
    vjson = launcher.load_version(version_id)       # 失败时抛 LaunchError

    missing: list[MissingItem] = []
    checked = 0

    # 1) 客户端 jar
    jar_path, jar_ok = _jar_path(launcher, version_id, vjson)
    checked += 1
    if not jar_ok:
        client = (vjson.get("downloads") or {}).get("client") or {}
        missing.append(MissingItem(
            kind="jar",
            name="客户端 jar",
            path=jar_path,
            url=str(client.get("url") or ""),
            sha1=str(client.get("sha1") or ""),
            size=int(client.get("size") or 0),
        ))

    # 2) 库文件
    for lib in resolve_libraries(vjson):
        checked += 1
        path = game_dir / "libraries" / Path(lib.path)
        if path.is_file():
            continue
        missing.append(MissingItem(
            kind="library",
            name=lib.name or lib.path,
            path=path,
            url=lib.url or "",
            sha1=lib.sha1 or "",
            size=int(lib.size or 0),
        ))

    # 3) 资源索引 + 4) 索引里的资源对象
    index = asset_index_of(vjson)
    if index:
        checked += 1
        index_path = game_dir / "assets" / "indexes" / f"{index.id}.json"
        index_json = _read_index(index_path)
        if index_json is None:
            missing.append(MissingItem(
                kind="index",
                name=f"资源索引 {index.id}",
                path=index_path,
                url=index.url or "",
                sha1=index.sha1 or "",
                size=int(index.size or 0),
            ))
        else:
            seen: set[str] = set()
            for h, rel, size in asset_objects(index_json):
                if rel in seen:
                    continue
                seen.add(rel)
                checked += 1
                path = game_dir / "assets" / "objects" / rel
                if path.is_file():
                    continue
                missing.append(MissingItem(
                    kind="asset",
                    name=rel,
                    path=path,
                    url=f"{ASSETS_URL}/{rel}",
                    sha1=h,
                    size=int(size or 0),
                ))

    return CheckReport(
        version_id=version_id,
        jar_ok=jar_ok,
        checked=checked,
        missing=missing,
    )


# ---------------------------------------------------------------- 补全

def repair(
    game_dir: Path,
    version_id: str,
    on_log: Callable[[str], None] = lambda _m: None,
    progress_cb: Callable[[Progress], None] | None = None,
    cancel: threading.Event | None = None,
    threads: int = 16,
    source: str = "official",
) -> tuple[bool, str]:
    """校验并补全缺失文件，返回 (最终是否完整, 结果描述)。

    ``cancel`` 被 set 时中止下载并返回 ``(False, "已取消")``。
    """
    game_dir = Path(game_dir)
    log = on_log or (lambda _m: None)

    if _cancelled(cancel):
        return False, "已取消"

    try:
        report = check(game_dir, version_id)
    except LaunchError as exc:
        return False, f"读取版本失败：{exc}"

    if report.ok:
        return True, "文件完整"

    log(report.summary())
    fixed = 0

    # 资源索引本身是资源清单：先补索引，重新检查后才能展开资源对象
    index_items = [item for item in report.missing if item.kind == "index"]
    if index_items:
        for item in index_items:
            if _cancelled(cancel):
                return False, "已取消"
            if not item.url:
                log(f"缺少下载地址，跳过：{item.name}")
                continue
            try:
                text = fetch_text(item.url, source=source)
                if not isinstance(json.loads(text), dict):
                    raise ValueError("索引内容不是 JSON 对象")
                item.path.parent.mkdir(parents=True, exist_ok=True)
                item.path.write_text(text, encoding="utf-8")
                fixed += 1
                log(f"已补全：{item.name}")
            except Exception as exc:                 # noqa: BLE001 - 网络与解析异常统一记录
                log(f"补全失败：{item.name}（{type(exc).__name__}: {exc}）")
        if _cancelled(cancel):
            return False, "已取消"
        try:
            report = check(game_dir, version_id)
        except LaunchError as exc:
            return False, f"读取版本失败：{exc}"

    # 其余缺失项统一转成下载任务
    tasks: list[DownloadTask] = []
    for item in report.missing:
        if item.kind == "index":
            continue                     # 索引已单独处理（可能仍然缺失）
        if not item.url:
            log(f"缺少下载地址，跳过：{item.name}")
            continue
        tasks.append(DownloadTask(
            url=item.url,
            dest=item.path,
            sha1=item.sha1 or None,
            size=item.size or None,
        ))

    if tasks:
        if _cancelled(cancel):
            return False, "已取消"
        log(f"需要补全 {len(tasks)} 个文件…")
        downloader = Downloader(threads=threads)
        if cancel is not None:
            downloader.cancelled = cancel      # 外部取消信号直接接管下载器
        try:
            ok_count, bad_count = downloader.run(
                tasks,
                source=source,
                progress_cb=progress_cb,
                on_log=log,
            )
        except Exception as exc:                     # noqa: BLE001
            return False, f"补全失败：{type(exc).__name__}: {exc}"
        fixed += ok_count
        if bad_count:
            log(f"{bad_count} 个文件下载失败")
        if _cancelled(cancel):
            return False, "已取消"

    try:
        final = check(game_dir, version_id)
    except LaunchError as exc:
        return False, f"读取版本失败：{exc}"

    if final.ok:
        return True, f"补全 {fixed} 项，文件完整"
    return False, f"补全 {fixed} 项，仍缺 {len(final.missing)} 项"
