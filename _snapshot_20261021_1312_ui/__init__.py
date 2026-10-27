"""MCLite —— 轻量级 Minecraft 启动器。

模块划分：
    config      配置持久化、默认路径
    downloader  多线程下载、镜像替换、SHA1 校验、进度回调
    versionmeta 版本清单、版本 JSON 解析、规则匹配、classpath/natives 计算
    java        Java 运行时检测与版本识别
    installer   下载并安装一个完整的 Minecraft 版本
    launcher    组装命令行并启动游戏（支持 inheritsFrom 继承）
    loaders     Forge / NeoForge / Fabric 加载器安装
    auth        微软正版登录（设备码流程 → XBL → XSTS → Minecraft）
    accounts    多账号管理（正版 + 离线，可切换）
    mods        mods 目录管理
    modrinth    Modrinth 搜索与下载（模组 / 资源包 / 光影）
    modpack     整合包（.mrpack）解析、下载、解包与实例生成
    instances   实例隔离（每个版本独立游戏目录）
    javaauto    Java 运行时自动下载（Mojang java-runtime）
    skin_sites  第三方皮肤站认证（Yggdrasil + authlib-injector）
    crash       崩溃日志诊断
    feedback    一键反馈打包
    worlds      存档管理（NBT 读名字、zip 备份 / 恢复 / 删除）
    verify      完整性检查与一键修复
    exportpack  把实例导出成 .mrpack
    packdetect  整合包格式识别（Modrinth / CurseForge / MultiMC / 散装 zip）
    curseforge  CurseForge 整合包的模组自动下载（免 API Key，拼 CDN 直链）
    skins       皮肤读取与上传（Mojang + 第三方皮肤站）
    cnsearch    中文关键词 → 英文搜索词（模组中文搜索）
    ui          tkinter 界面
"""

__version__ = "1.5.0"
APP_NAME = "MCLite"
