"""崩溃诊断：从启动日志 / crash-report 里认出常见故障，翻译成中文结论和建议。

只用正则做启发式判断——启动器没必要重新发明 Java 堆栈解析器，能命中几十种
最常见的失败原因、并且把原始报错摘要摆出来，就比让用户对着几千行日志发呆强。

规则按"越具体越靠前"排：更精确的规则先命中，宽泛的兜底（caused_by）放最后。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Diagnosis:
    title: str
    detail: str = ""
    hints: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        parts = [self.title]
        if self.detail:
            parts.append(self.detail)
        if self.hints:
            parts.append("")
            parts.extend(f"· {h}" for h in self.hints)
        return "\n".join(parts)


@dataclass
class _Rule:
    key: str
    pattern: re.Pattern
    title: str
    hints: list[str]
    detail_group: int | None = None


_RULES: list[_Rule] = [
    _Rule(
        "metaspace",
        re.compile(r"OutOfMemoryError:\s*Metaspace|OutOfMemoryError:\s*Compressed class space"),
        "元空间（Metaspace）用满了",
        ["模组装得太多，类定义把元空间撑爆了：把不用的模组删掉一批",
         "在「附加 JVM 参数」里加「-XX:MaxMetaspaceSize=512m」再试一次",
         "同一条日志里如果还有别的 OutOfMemoryError，以那条为主"],
    ),
    _Rule(
        "heap_size",
        re.compile(r"Invalid maximum heap size|Invalid initial heap size|"
                   r"Could not reserve enough space for object heap|"
                   r"Could not reserve enough space for (\d+)KB object heap"),
        "内存参数没被 Java 接受（启动参数里的 -Xmx 不合适）",
        ["「设置 → 内存」别超过物理内存的一半，32 位 Java 最多 1.5 GB",
         "检查「附加 JVM 参数」里是不是有写错的 -Xmx / -Xms"],
    ),
    _Rule(
        "jvm_option",
        re.compile(r"Unrecognized VM option|Error: Could not create the Java Virtual Machine|"
                   r"Error occurred during initialization of VM|"
                   r"Unrecognized option:"),
        "JVM 起不来（启动参数里有这个 Java 不认识的选项）",
        ["「设置 → 附加 JVM 参数」里可能有当前 Java 版本不支持的参数（比如给 Java 8 传了 Java 17 的 GC 参数）",
         "先把附加参数清空试一次，能启动后再一项项加回来"],
    ),
    _Rule(
        "java_bitness",
        re.compile(r"JVM is 32-bit|32 位|This Java instance does not support a 32-bit JVM|"
                   r"not a valid Win32 application", re.I),
        "Java 位数不对（32 位 Java 撑不起大内存）",
        ["换 64 位 Java：官方启动器在 %APPDATA%\\.minecraft\\runtime 下的都是 64 位",
         "「设置 → Java 运行时」点「检测」会列出每个 Java 的位数，选带 64 位的那个"],
    ),
    _Rule(
        "module_conflict",
        re.compile(r"java\.lang\.module\.ResolutionException|"
                   r"module .* does not read|Modules? .* and .* export package"),
        "模组之间抢同一个包（Java 模块冲突）",
        ["常见于 Forge / NeoForge 的启动环境重复塞了原版 jar",
         "把「设置 → 附加 JVM 参数」里手写的 -cp / --module-path 删掉，让启动器自己拼"],
    ),
    _Rule(
        "dll_missing",
        re.compile(r"VCRUNTIME140|MSVCP140|api-ms-win-crt|"
                   r"The code execution cannot proceed because", re.I),
        "系统缺少运行库（VC++ 运行库 / UCRT）",
        ["装一遍「Microsoft Visual C++ 运行库合集（x64）」再启动",
         "Windows 7 还需要装 SHA-2 补丁和 UCRT 更新"],
    ),
    _Rule(
        "jar_corrupt",
        re.compile(r"invalid LOC header|zip file is empty|error in opening zip file|"
                   r"zip END header not found|invalid CEN header|"
                   r"java\.util\.zip\.ZipException", re.I),
        "有 jar 文件下载坏了（zip 结构不完整）",
        ["到「开始」页选中这个版本，点「校验文件」让启动器重新下载坏掉的那个",
         "内存不足 / 硬盘写满时下载的文件也会坏，顺手看一下剩余空间"],
    ),
    _Rule(
        "oom",
        re.compile(r"java\.lang\.OutOfMemoryError(?::\s*([^\r\n]+))?"),
        "游戏内存不够（OutOfMemoryError）",
        ["到「设置 → 内存」把内存调大一点，模组多的话 4 GB 起步、6~8 GB 更稳",
         "32 位 Java 最多只能用 1.5 GB 左右，确认用的是 64 位 Java",
         "光影/大整合包请同时关掉其它吃内存的程序"],
        1,
    ),
    _Rule(
        "class_version",
        re.compile(r"UnsupportedClassVersionError.*?class file version (\d+)"),
        "Java 版本太低，跑不动这个版本的游戏或模组",
        ["换成本版本需要的 Java：1.17+ 用 Java 17，1.20.5+ 用 Java 21",
         "可以在「设置 → Java 运行时」里点「检测」看已装了哪些 Java"],
        1,
    ),
    _Rule(
        "missing_dep",
        re.compile(r"Missing or unsupported mandatory dependencies|"
                   r"Mod ID:\s*'?([\w\-]+)'?,\s*Requested by", re.I),
        "缺少前置模组 / 模组依赖不满足",
        ["按报错里提到的模组名去 Modrinth 或 CurseForge 补齐前置",
         "常见前置：Fabric API、Architectury API、Cloth Config、Kotlin for Forge"],
    ),
    _Rule(
        "duplicate_mod",
        re.compile(r"Duplicate mods found|DuplicateModsFoundException"),
        "mods 文件夹里有重复的模组",
        ["同一个模组放了两个版本（比如 xxx-1.0.jar 和 xxx-1.1.jar），删掉旧的那个"],
    ),
    _Rule(
        "no_such_method",
        re.compile(r"java\.lang\.(?:NoSuchMethodError|NoClassDefFoundError|"
                   r"ClassNotFoundException|IncompatibleClassChangeError):?\s*([^\r\n]{0,120})"),
        "模组版本不匹配（找不到类或方法）",
        ["确认模组和游戏版本、加载器版本都对应（1.20.1 的模组别放进 1.21）",
         "整合包升级时把旧版本残留的模组删干净"],
        1,
    ),
    _Rule(
        "mixin",
        re.compile(r"org\.spongepowered\.asm\.mixin\.(?:throwables\.)?MixinApplyError|"
                   r"Mixin apply failed|InvalidInjectionException"),
        "Mixin 注入失败（多半是模组之间不兼容）",
        ["先只保留必须的模组，确认能进游戏后再一个个加回来定位冲突",
         "检查 OptiFine 与 Fabric 的替代品（Iris/Sodium）是否装错组合"],
    ),
    _Rule(
        "glfw",
        re.compile(r"GLFW error (65542|65539|65543)|Pixel format not accelerated|"
                   r"Failed to create (?:window|context)|WGL: The driver does not appear"),
        "显卡驱动 / OpenGL 初始化失败",
        ["更新显卡驱动（NVIDIA / AMD / Intel 官方驱动，不是系统自带的那份）",
         "远程桌面或虚拟机里通常没有 OpenGL，改用本机运行",
         "双显卡笔记本确认游戏跑在独显上"],
    ),
    _Rule(
        "library",
        re.compile(r"Failed to download|Couldn't download|"
                   r"java\.io\.FileNotFoundException.*?libraries", re.I),
        "游戏文件下载不完整",
        ["到「下载」页重新安装这个版本，启动器会自动补齐缺失文件",
         "下载源可以在「设置」里换成 BMCLAPI 镜像再试"],
    ),
    _Rule(
        "auth",
        re.compile(r"InvalidCredentialsException|AuthenticationException|"
                   r"Failed to verify username|status code 401"),
        "登录凭据无效（离线启动时出现属正常现象）",
        ["正版账号：到账号管理里重新登录一次",
         "离线启动时这条可以忽略，正版服务器会拒绝离线玩家"],
    ),
    _Rule(
        "java_missing",
        re.compile(r"Unable to locate a Java Runtime|no suitable Java|"
                   r"'java' 不是内部或外部命令"),
        "找不到可用的 Java",
        ["到「设置 → Java 运行时」点「检测」，或手动指定 java.exe 的路径"],
    ),
    _Rule(
        "access_violation",
        re.compile(r"EXCEPTION_ACCESS_VIOLATION|exit code[:\s]+-1073741819|"
                   r"0xC0000005", re.I),
        "进程被显卡驱动或本地库直接干掉了（内存访问越界）",
        ["更新显卡驱动；笔记本双显卡时强制用独显",
         "关掉游戏内的光影或高负载画面设置再试",
         "如果装了优化模组（Sodium / OptiFine），换一个版本试试"],
    ),
    _Rule(
        "mod_loading",
        re.compile(r"ModLoadingException|LoadingErrors|Fatal error in mod loading|"
                   r"Failed to (?:load|create) mod|An exception occurred while loading mods?|"
                   r"Mod loading (?:has )?failed", re.I),
        "模组加载阶段就失败了",
        ["日志里紧跟在后面那条 Caused by 才是真正的报错，先看它",
         "把最近新加的模组挪出 mods 文件夹，确认能进游戏后再放回来"],
    ),
    _Rule(
        "invalid_mod",
        re.compile(r"Invalid mod file|Mod file .{0,80} is not valid|"
                   r"not a valid mod file|Failed to read .{0,80}\.jar|"
                   r"Could not find or load main class net\.minecraft", re.I),
        "有模组文件不是有效模组（或模组放错了位置）",
        ["把那个 jar 从 mods 里删掉，重新从下载页下一个",
         "有些包是「资源包 / 光影 / 数据包」，要放到对应文件夹，不能丢进 mods"],
    ),
    _Rule(
        "fabric_api",
        re.compile(r"requires (?:any version of )?(?:the )?(?:Fabric API|fabric-api|fabricloader)|"
                   r"Fabric API .{0,40}(?:not installed|missing)|"
                   r"requires fabricloader", re.I),
        "缺少 Fabric API",
        ["到「Mod」页搜「Fabric API」装上，版本和游戏版本对应",
         "Quilt 用户装 Quilted Fabric API"],
    ),
    _Rule(
        "optifine",
        re.compile(r"OptiFine.{0,120}(?:Fabric|Iris|not compatible|incompatible)|"
                   r"(?:Fabric|Iris).{0,120}OptiFine.{0,40}(?:not|in)compatible", re.I),
        "OptiFine 和当前加载器 / 光影模组冲突",
        ["Fabric 上别装 OptiFine：用 Sodium + Iris 替代",
         "Forge 上如果同时装了 OptiFine 和 Oculus，二者只能留一个"],
    ),
    _Rule(
        "sodium_gl",
        re.compile(r"Sodium.{0,160}(?:OpenGL 4\.|GL_[A-Z]|unsupported (?:GPU|graphics)|"
                   r"requires OpenGL)|Iris.{0,120}requires|"
                   r"Your GPU (?:is not supported|does not support)", re.I | re.S),
        "显卡 / 驱动不满足优化模组的要求",
        ["更新显卡驱动；Sodium 需要 OpenGL 4.5 以上",
         "集成显卡或远程桌面往往不满足，换本机独显运行"],
    ),
    _Rule(
        "registry_dup",
        re.compile(r"Duplicate registry entry|already (?:registered|defined)|"
                   r"Trying to set .{0,40} twice|IllegalStateException: Duplicate", re.I),
        "两个模组注册了同一个物品 / 方块 / 配方",
        ["多半是同一个模组装了新旧两个版本，检查 mods 里的重复项",
         "整合包里自带了某个模组、你又手动加了一遍也会有这个报错"],
    ),
    _Rule(
        "tick_loop",
        re.compile(r"Exception ticking (?:world|entity|block entity|screen)|"
                   r"Ticking (?:entity|block entity)|"
                   r"The game crashed whilst ticking"),
        "游戏运行中某个实体 / 方块把主循环弄崩了",
        ["这类崩溃几乎都指向具体模组：看报错里的类名属于哪个模组",
         "先在创造模式单人世界复现，确认后把可疑模组挪走"],
    ),
    _Rule(
        "world_corrupt",
        re.compile(r"Failed to load (?:world|level|chunk)|"
                   r"(?:level|world|chunk) .{0,40}(?:is )?corrupt|"
                   r"Region file .{0,80} is corrupt", re.I),
        "存档有损坏的区块",
        ["到「开始」页的「存档」里先备份这个存档，再来回试",
         "装了新模组后存档打不开，多半是模组删掉了导致方块 / 实体丢失"],
    ),
    _Rule(
        "resourcepack",
        re.compile(r"Failed to load resource pack|Couldn't load .{0,60}pack|"
                   r"pack\.mcmeta|Invalid pack format", re.I),
        "资源包 / 光影包格式不对",
        ["确认资源包和游戏版本对应（pack_format 不匹配会这样）",
         "把 resourcepacks 里最近放进去的那个挪走再试"],
    ),
    _Rule(
        "server_conn",
        re.compile(r"java\.net\.(?:ConnectException|UnknownHostException|SocketTimeoutException)|"
                   r"Connection (?:refused|reset)|Failed to connect to|"
                   r"io\.netty\.channel\..{0,40}(?:Exception|Error)"),
        "连不上服务器（网络 / 地址问题）",
        ["确认服务器地址和端口没写错，服务器是否在线",
         "开了代理 / 加速器时试试关掉；局域网联机要同一网段并允许防火墙"],
    ),
    _Rule(
        "disk_full",
        re.compile(r"No space left on device|There is not enough space|"
                   r"磁盘空间不足|not enough space on the disk", re.I),
        "硬盘空间不足",
        ["清一下游戏目录里的旧日志 / 旧版本，或者把游戏目录换到空间大的盘",
         "整合包 + 光影动辄几十 GB，留 10 GB 以上余量比较稳"],
    ),
    _Rule(
        "access_denied",
        re.compile(r"AccessDeniedException|Permission denied|拒绝访问|"
                   r"java\.io\.FileNotFoundException.{0,80}(?:Access|denied)", re.I),
        "文件被占用或没有权限",
        ["游戏目录别放在 C:\\Program Files 这类受保护目录里",
         "杀毒软件 / 网盘同步可能锁着 jar，把游戏目录加白名单"],
    ),
    _Rule(
        "audio",
        re.compile(r"Failed to open (?:OpenAL|device)|OpenAL.{0,60}(?:not found|error)|"
                   r"SoundSystem.{0,40}(?:error|failed)|"
                   r"AL lib:", re.I),
        "声音设备初始化失败（一般不影响进游戏）",
        ["蓝牙耳机 / 虚拟声卡切走再切回来，或者换一个默认播放设备",
         "这条通常只是噪音，游戏能进就不用管"],
    ),
    _Rule(
        "lwjgl_natives",
        re.compile(r"Failed to locate library|UnsatisfiedLinkError.{0,120}(?:lwjgl|\.dll)|"
                   r"org\.lwjgl\.system\.Library|no lwjgl.{0,20}in java\.library\.path", re.I),
        "本机库（native .dll）没找到",
        ["版本目录下的 natives 被删了：到「开始」页点「校验文件」补齐",
         "把杀毒软件拦下来的 dll 恢复回来，或者信任整个游戏目录"],
    ),
    _Rule(
        "shader_error",
        re.compile(r"Shader (?:compilation )?failed|Failed to compile (?:shader|program)|"
                   r"Iris.{0,60}(?:shader|program).{0,40}(?:error|fail)", re.I | re.S),
        "光影编译失败",
        ["换一个光影版本，或者把光影包更新到支持当前 Iris / OptiFine 的版本",
         "部分光影需要特定的 Sodium / Iris 组合，先关掉光影确认能进游戏"],
    ),
    _Rule(
        "caused_by",
        re.compile(r"Caused by:\s*([^\r\n]{0,200})"),
        "找到一条根因报错",
        ["把这条报错连同日志一起发到模组作者的问题追踪里通常就能定位"],
        1,
    ),
]

_DESC = re.compile(r"Description:\s*([^\r\n]{0,200})")
_CRASH_LINE = re.compile(r"The game crashed whilst ([^\r\n]{0,120})")


def analyze(text: str, limit: int = 4) -> list[Diagnosis]:
    """扫一遍文本，命中越靠前的规则优先级越高。"""
    if not text:
        return []
    out: list[Diagnosis] = []
    seen: set[str] = set()
    for rule in _RULES:
        if rule.key in seen:
            continue
        m = rule.pattern.search(text)
        if not m:
            continue
        seen.add(rule.key)
        detail = ""
        if rule.detail_group is not None:
            try:
                captured = (m.group(rule.detail_group) or "").strip()
            except IndexError:
                captured = ""
            detail = captured
        if rule.key == "caused_by" and not detail:
            continue
        out.append(Diagnosis(rule.title, detail, list(rule.hints)))
        if len(out) >= limit:
            break
    return out


def describe(text: str) -> str:
    """给日志末尾一句人话总结，用在状态栏 / 弹窗标题。"""
    if not text:
        return ""
    m = _CRASH_LINE.search(text)
    if m:
        return m.group(1).strip()
    m = _DESC.search(text)
    if m:
        return m.group(1).strip()
    diags = analyze(text, limit=1)
    return diags[0].title if diags else ""


def latest_log(game_dir: str | Path, version_id: str | None = None) -> Path | None:
    """找最近一次游戏日志：优先启动器自己写的那份，其次官方 launcher 的 latest.log。"""
    logs = Path(game_dir) / "logs"
    if not logs.is_dir():
        return None
    if version_id:
        own = logs / f"mclite-{version_id}-latest.log"
        if own.is_file():
            return own
    candidates = [p for p in logs.glob("*.log") if p.is_file()]
    candidates += [p for p in logs.glob("*.log.gz") if p.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def latest_crash_report(game_dir: str | Path) -> Path | None:
    folder = Path(game_dir) / "crash-reports"
    if not folder.is_dir():
        return None
    files = [p for p in folder.glob("crash-*.txt") if p.is_file()]
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def analyze_game_dir(game_dir: str | Path, version_id: str | None = None,
                     log_path: str | Path | None = None) -> tuple[list[Diagnosis], Path | None]:
    """把最近的日志和崩溃报告一起分析，返回 (诊断列表, 用到的文件)。"""
    text = ""
    used: Path | None = None
    report = latest_crash_report(game_dir)
    if report is not None:
        try:
            text = report.read_text(encoding="utf-8", errors="replace")
            used = report
        except OSError:
            text = ""
    path = Path(log_path) if log_path else latest_log(game_dir, version_id)
    if path is not None and path.is_file():
        try:
            tail = _read_tail(path, 200_000)
        except OSError:
            tail = ""
        if tail:
            text = tail if not text else text + "\n" + tail
            used = used or path
    return analyze(text), used


def _read_tail(path: Path, size: int) -> str:
    with open(path, "rb") as fh:
        fh.seek(0, 2)
        total = fh.tell()
        fh.seek(max(0, total - size))
        data = fh.read()
    return data.decode("utf-8", errors="replace")
