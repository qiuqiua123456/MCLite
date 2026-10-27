"""Modrinth 客户端：搜索模组、列出适用文件、下载到 mods 目录。

只依赖标准库。API 文档：https://docs.modrinth.com/api-spec
"""

from __future__ import annotations

import json
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .downloader import DownloadTask, Downloader, human_size

API = "https://api.modrinth.com/v2"

# 加载器 -> Modrinth 分类名
LOADERS = {
    "fabric": "fabric",
    "forge": "forge",
    "neoforge": "neoforge",
    "quilt": "quilt",
}

SOURCE_NAMES = {"fabric": "Fabric", "forge": "Forge", "neoforge": "NeoForge",
                "quilt": "Quilt", "vanilla": "原版"}

# 内容类型 → (游戏目录下的子目录, 中文名)
CONTENT_TYPES: dict[str, tuple[str, str]] = {
    "mod": ("mods", "模组"),
    "resourcepack": ("resourcepacks", "资源包"),
    "shader": ("shaderpacks", "光影"),
    "modpack": ("modpacks", "整合包"),
}


def target_dir(game_dir: str | Path, project_type: str = "mod") -> Path:
    """按内容类型算出该存到哪个目录（目录不存在就建出来）。"""
    sub = CONTENT_TYPES.get(project_type, ("mods", "模组"))[0]
    path = Path(game_dir) / sub
    path.mkdir(parents=True, exist_ok=True)
    return path


def _get(path: str, **params: Any) -> Any:
    url = API + path
    if params:
        clean = {k: v for k, v in params.items() if v not in (None, "", [])}
        if clean:
            url += "?" + urllib.parse.urlencode(clean)
    from .downloader import fetch_json
    return fetch_json(url, timeout=20)


@dataclass
class ModProject:
    project_id: str
    slug: str
    title: str
    description: str
    downloads: int
    categories: list[str] = field(default_factory=list)
    loaders: list[str] = field(default_factory=list)
    versions: list[str] = field(default_factory=list)
    icon_url: str = ""

    @property
    def downloads_label(self) -> str:
        n = self.downloads
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.1f}K"
        return str(n)

    @property
    def loader_label(self) -> str:
        # 搜索结果里 loaders 常为空，加载器实际混在 categories 里
        candidates = [l for l in self.loaders if l in LOADERS]
        if not candidates:
            candidates = [c for c in self.categories if c in LOADERS]
        names = [SOURCE_NAMES.get(l, l) for l in candidates[:2]]
        return " / ".join(names)


@dataclass
class ModFile:
    url: str
    filename: str
    size: int = 0
    sha1: str = ""
    version_name: str = ""
    game_versions: list[str] = field(default_factory=list)
    loaders: list[str] = field(default_factory=list)
    release_type: str = "release"

    @property
    def size_label(self) -> str:
        return human_size(self.size)


@dataclass
class ModVersion:
    version_id: str
    name: str
    version_number: str
    game_versions: list[str] = field(default_factory=list)
    loaders: list[str] = field(default_factory=list)
    downloads: int = 0
    date: str = ""
    files: list[ModFile] = field(default_factory=list)


def search(
    query: str,
    game_version: str = "",
    loader: str = "",
    limit: int = 20,
    offset: int = 0,
    project_type: str = "mod",
    index: str = "downloads",
) -> tuple[list[ModProject], int]:
    """搜索内容，返回 (结果列表, 匹配总数)。`project_type` 可以是 mod / resourcepack / shader / modpack。

    ``index`` 决定排序：``downloads`` 最热门（默认）、``relevance`` 最相关、
    ``updated`` 最近更新、``newest`` 最新发布。空关键字时用 ``downloads``
    也能直接列出热门内容（用户反馈「不搜索就不显示结果」）。
    """
    facets: list[list[str]] = [[f"project_type:{project_type or 'mod'}"]]
    if game_version:
        facets.append([f"versions:{game_version}"])
    # 整合包的加载器同样挂在 categories 上（fabric / forge / neoforge / quilt）
    if loader and project_type in ("mod", "modpack"):
        facets.append([f"categories:{loader}"])
    data = _get(
        "/search",
        query=query,
        limit=limit,
        offset=offset,
        index=index or "downloads",
        facets=json.dumps(facets, separators=(",", ":")),
    )
    hits = data.get("hits") or []
    out: list[ModProject] = []
    for h in hits:
        out.append(ModProject(
            project_id=h.get("project_id", ""),
            slug=h.get("slug", ""),
            title=h.get("title", "?"),
            description=h.get("description", ""),
            downloads=int(h.get("downloads") or 0),
            categories=list(h.get("categories") or []),
            loaders=list(h.get("loaders") or []),
            versions=list(h.get("versions") or []),
            icon_url=h.get("icon_url") or "",
        ))
    return out, int(data.get("total_hits") or 0)


def versions(
    project_id: str,
    game_version: str = "",
    loader: str = "",
) -> list[ModVersion]:
    """列出某个模组的版本文件，优先返回适配当前版本/加载器的。"""
    params: dict[str, Any] = {}
    if game_version:
        params["game_versions"] = json.dumps([game_version])
    if loader:
        params["loaders"] = json.dumps([loader])
    data = _get(f"/project/{project_id}/version", **params)
    if not isinstance(data, list):
        return []
    out: list[ModVersion] = []
    for v in data:
        files = []
        for f in v.get("files") or []:
            if not f.get("url"):
                continue
            files.append(ModFile(
                url=f["url"],
                filename=f.get("filename") or Path(f["url"]).name,
                size=int(f.get("size") or 0),
                sha1=(f.get("hashes") or {}).get("sha1", ""),
                version_name=v.get("version_number", ""),
                game_versions=list(v.get("game_versions") or []),
                loaders=list(v.get("loaders") or []),
                release_type=v.get("version_type", "release"),
            ))
        if not files:
            continue
        out.append(ModVersion(
            version_id=v.get("id", ""),
            name=v.get("name", ""),
            version_number=v.get("version_number", ""),
            game_versions=list(v.get("game_versions") or []),
            loaders=list(v.get("loaders") or []),
            downloads=int(v.get("downloads") or 0),
            date=(v.get("date_published") or "")[:10],
            files=files,
        ))
    return out


def primary_file(version: ModVersion) -> ModFile | None:
    for f in version.files:
        if f.release_type:
            return f
    return version.files[0] if version.files else None


def download(
    files: list[ModFile],
    target_dir: Path,
    threads: int = 4,
    progress_cb=None,
    on_log=None,
) -> tuple[int, int]:
    """把文件下载到目标目录（mods / resourcepacks / shaderpacks），返回 (成功, 失败)。"""
    target_dir = Path(target_dir)
    tasks = [
        DownloadTask(url=f.url, dest=target_dir / f.filename,
                     sha1=f.sha1 or None, size=f.size or None)
        for f in files
    ]
    dl = Downloader(threads=threads)
    return dl.run(tasks, source="official", progress_cb=progress_cb, on_log=on_log)


def detect_loader(game_dir: Path, version_id: str) -> str:
    """根据版本 ID 或已装 mods 猜测加载器。"""
    low = version_id.lower()
    for key in ("neoforge", "forge", "fabric", "quilt"):
        if key in low:
            return key
    # 看版本 JSON 的 libraries
    try:
        vjson_path = Path(game_dir) / "versions" / version_id / f"{version_id}.json"
        text = vjson_path.read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        return ""
    if "neoforge" in text:
        return "neoforge"
    if "fabric-loader" in text or "net.fabricmc" in text:
        return "fabric"
    if "quilt" in text:
        return "quilt"
    if "minecraftforge" in text or "forge" in text:
        return "forge"
    return ""
