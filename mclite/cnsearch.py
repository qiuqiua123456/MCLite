"""中文搜索词 → Modrinth 英文关键词。

Modrinth 的搜索索引里几乎没有中文，直接搜「钠」「优化」都是 0 结果。
这里维护一份常用词表，把输入里的中文片段按最长匹配替换成英文，
让用户可以用中文关键字找模组 / 资源包 / 光影。

设计取舍：
- 只做词表替换，不联网翻译——稳定、快、离线可用；
- 中文片段按长度从长到短匹配，保证「小地图」不会先被「地图」吃掉；
- 词表里没有的中文一律丢掉（留着只会让结果变成 0），并在返回值里
  告诉 UI 实际用了哪些词，方便提示用户。
"""

from __future__ import annotations

# 中文词 → 英文搜索词。键按长度从长到短匹配，不用手动排序。
_MAP: dict[str, str] = {
    # ---- 性能 / 优化（中文社区最常见的一类）
    "高清修复": "optifine",
    "帧数优化": "fps",
    "内存优化": "memory",
    "性能优化": "performance",
    "优化": "optimization",
    "性能": "performance",
    "加速": "performance",
    "钠": "sodium",
    "铷": "rubidium",
    "锂": "lithium",
    "磷": "phosphor",
    "铱": "iris",
    "氪": "krypton",
    "铁氧体": "ferritecore",
    "实体优化": "entity culling",
    "光影": "shaders",
    "光影包": "shaders",
    "高清": "optifine",
    "帧数": "fps",
    # ---- 界面 / HUD
    "小地图": "minimap",
    "抬头显示": "hud",
    "界面": "ui",
    "背包": "inventory",
    "物品栏": "inventory",
    "合成表": "jei",
    "配方": "recipe",
    "任务": "quest",
    "指南": "guide",
    "地图": "map",
    "字体": "font",
    "动画": "animation",
    # ---- 内容 / 玩法
    "装饰": "decoration",
    "家具": "furniture",
    "建筑": "building",
    "农业": "farming",
    "种植": "farming",
    "食物": "food",
    "料理": "food",
    "科技": "tech",
    "机器": "machines",
    "能源": "energy",
    "电力": "energy",
    "自动化": "automation",
    "管道": "pipes",
    "魔法": "magic",
    "法术": "spell",
    "附魔": "enchantment",
    "符文": "rune",
    "冒险": "adventure",
    "地牢": "dungeon",
    "生物": "mob",
    "怪物": "mob",
    "村庄": "village",
    "传送石": "waystone",
    "传送门": "portal",
    "传送": "teleport",
    "存储": "storage",
    "储物": "storage",
    "收纳": "storage",
    "仓库": "storage",
    "箱子": "chest",
    "武器": "weapon",
    "装备": "equipment",
    "护甲": "armor",
    "工具": "tools",
    "战斗": "combat",
    "弓箭": "bow",
    "载具": "vehicle",
    "汽车": "car",
    "飞机": "plane",
    "红石": "redstone",
    "林业": "forestry",
    "钓鱼": "fishing",
    "宠物": "pet",
    "驯服": "tame",
    "迷宫": "maze",
    "生存": "survival",
    "创造": "creative",
    # ---- 资源 / 视觉
    "材质包": "resourcepack",
    "资源包": "resourcepack",
    "材质": "resourcepack",
    "音效": "sound",
    "音乐": "music",
    "动态光源": "dynamic lights",
    "连接材质": "connected textures",
    "粒子": "particles",
    # ---- 功能 / 其它
    "汉化": "translation",
    "中文": "chinese",
    "翻译": "translation",
    "修复": "fix",
    "兼容": "compatibility",
    "前置": "api",
    "库": "library",
    "服务器": "server",
    "多人": "multiplayer",
    "联机": "multiplayer",
    "整合包": "modpack",
    "数据包": "datapack",
    "模组": "mod",
    "作弊": "cheat",
    "自动": "auto",
    "快捷": "quick",
    "种子": "seed",
    "菜单": "menu",
    "设置": "config",
}



def has_cjk(text: str) -> bool:
    """是否含中日韩字符（用来判断要不要翻译）。"""
    return any("\u4e00" <= ch <= "\u9fff" for ch in text or "")


def _keys() -> list[str]:
    return sorted(_MAP, key=len, reverse=True)


def translate(text: str) -> tuple[str, str]:
    """把中文查询转成英文查询。

    返回 ``(英文查询, 提示)``：
    - 没有中文时原样返回，提示为空；
    - 有中文时按最长匹配替换，未识别的中文片段丢弃；
    - 提示形如 ``钠 → sodium，优化 → optimization``，给 UI 显示用。
    """
    raw = (text or "").strip()
    if not raw or not has_cjk(raw):
        return raw, ""

    out: list[str] = []
    hits: list[str] = []
    i = 0
    while i < len(raw):
        matched = ""
        for key in _keys():
            if raw.startswith(key, i):
                matched = key
                break
        if matched:
            english = _MAP[matched]
            if english not in out:
                out.append(english)
            if f"{matched} → {english}" not in hits:
                hits.append(f"{matched} → {english}")
            i += len(matched)
            continue
        ch = raw[i]
        if has_cjk(ch) or ch.isspace() or ch in "-_":
            i += 1                    # 丢掉未识别的汉字和分隔符
            continue
        # 连续的英文 / 数字原样保留
        j = i
        while j < len(raw) and not has_cjk(raw[j]):
            j += 1
        piece = raw[i:j].strip()
        if piece and piece not in out:
            out.append(piece)
        i = j

    return " ".join(out), "，".join(hits)
