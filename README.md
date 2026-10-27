# MCLite

一个用 **Python + tkinter** 写的轻量 Minecraft 启动器，界面仿 PCL，全部逻辑只用标准库，可打包成**单个 exe**（无需安装 Python）。

```
F:\MCLite
├─ main.py                 入口
├─ mclite.spec             PyInstaller 打包配置
├─ mclite/
│  ├─ config.py            配置持久化（%APPDATA%\MCLite\config.json）
│  ├─ downloader.py        多线程下载器（镜像回退 + SHA1 校验 + 断点续传 + curl 兜底）
│  ├─ versionmeta.py       版本 JSON 解析（libraries / rules / arguments / assets）
│  ├─ installer.py         安装一个版本：client.jar + libraries + assets
│  ├─ java.py              Java 运行时检测与版本匹配
│  ├─ javaauto.py          Java 运行时自动下载（Mojang java-runtime 清单）
│  ├─ launcher.py          组装 classpath / 解压 natives / 拼命令行 / 拉起进程（支持 inheritsFrom 继承）
│  ├─ loaders.py           Forge / NeoForge / Fabric 加载器安装
│  ├─ instances.py         实例隔离（每个版本一个独立游戏目录）
│  ├─ modpack.py           整合包 .mrpack：解析 / 解包 / 装模组 / 生成实例
│  ├─ packdetect.py        拖入文件识别：Modrinth / CurseForge / MultiMC / 散装 zip
│  ├─ curseforge.py        CurseForge 模组自动下载（免 API Key，拼 CDN 直链）
│  ├─ exportpack.py        把实例导出成 .mrpack（含 mods / config / 覆盖文件）
│  ├─ worlds.py            存档管理（读 NBT 取世界名、zip 备份 / 恢复 / 删除）
│  ├─ verify.py            完整性检查与一键修复（jar / 库 / 资源逐个对 SHA1）
│  ├─ skins.py             皮肤读取与上传（Mojang + 第三方皮肤站材质）
│  ├─ auth.py              微软正版登录（设备码流程 → XBL → XSTS → Minecraft）
│  ├─ skin_sites.py        第三方皮肤站（Yggdrasil + authlib-injector）
│  ├─ accounts.py          多账号管理（正版 / 离线 / 皮肤站，可切换、可复制 UUID）
│  ├─ mods.py              mods 目录扫描、启用禁用、导入、删除
│  ├─ modrinth.py          Modrinth 搜索与下载（模组 / 资源包 / 光影 / 整合包）
│  ├─ crash.py             崩溃日志诊断（34 条常见故障规则）
│  ├─ feedback.py          一键反馈：日志 + 崩溃报告 + 模组清单 + 系统信息打包
│  ├─ cnsearch.py          中文关键词 → Modrinth 英文检索词（约 130 条常用译名）
│  └─ ui/                  界面（顶栏渐变 + 左栏账号卡，五套配色，自绘按钮/滑块/进度条）
│     ├─ app.py            主窗口：顶栏、左栏账户卡、页面容器、拖拽注册、主题重建
│     ├─ page_home.py      开始页：启动 / 模组 / 账户 三个页签
│     ├─ page_install.py   下载页：游戏版本 / 模组 / 资源包 / 光影 四个页签
│     ├─ page_settings.py  设置页
│     ├─ mods_panel.py     内嵌的模组管理面板（模组 / 资源包 / 光影 / 数据包）
│     ├─ accounts_panel.py 内嵌的账户管理面板（多账号切换 / 登录入口）
│     ├─ download_browser.py 内嵌的 Modrinth 浏览器（搜索 → 选版本 → 下载）
│     ├─ theme.py          五套配色 + 自绘控件 + ttk 样式
│     ├─ widgets.py        页签条 / 下拉 / 头像 / 日志面板 / 进度条 / Toast
│     └─ images.py         插画加载（只用 tk.PhotoImage，不依赖 Pillow）
└─ tools/                  截图、安装测试、启动测试、生成图标、打包发布
```

## 功能

顶栏只有三个入口：**开始 / 下载 / 设置**。模组管理和账户管理都收进了开始页的页签里，
下载页则把「装游戏」和「装模组 / 资源包 / 光影」并成了同一个页面的四个页签 —— 少一层跳转。

| 页面 | 页签 | 能做什么 |
| --- | --- | --- |
| **开始** | 启动 | 列出所有已装版本（原版 / Forge / Fabric / NeoForge / 整合包）→ 选一个 → 设置玩家名 / 内存 → 启动；实时显示游戏日志（**可折叠**）；删除版本；打开**该实例的**游戏目录 / 日志目录；**存档管理**（备份 / 恢复 / 删除世界）；**完整性检查**（一键补齐缺文件）；**导出整合包**（.mrpack）；**非正常退出时自动弹出崩溃诊断** |
| **开始** | 模组 | 按实例切换（自绘下拉，可切回共用目录），内容类型可选 **模组 / 资源包 / 光影 / 数据包**：启用 / 禁用（改后缀）、删除、导入本地文件、打开目录；右上「下载」直接跳到下载页对应页签 |
| **开始** | 账户 | 多账号列表（头像 + 类型 + 当前标记）、点一行即切换、复制离线 UUID、删除、添加离线账号、微软正版登录、第三方皮肤站登录、皮肤管理 |
| **下载** | 游戏版本 | 从 Mojang 拉 920+ 版本清单，按 全部 / 正式版 / 快照 / 远古版 过滤，**再按大版本号分组**（26.3 / 26.2 / 1.21 / 1.20 …）+ 大版本下拉 + 搜索版本号，一键下载安装（可随时取消）；选中版本后可**一键安装 Forge / NeoForge / Fabric / Quilt 加载器**（面板内嵌在页面里，不弹窗） |
| **下载** | 模组 / 资源包 / 光影 / 整合包 | **打开就有热门内容**（按下载量排序，不用先输关键字），输入关键字则按相关度搜；**支持中文关键词**（输入「小地图」自动换成 `minimap`、「优化」→ `optimization`、「钠」→ `sodium`）；版本筛选是下拉框；右栏选版本文件 → 下载并安装到当前实例 |
| **设置** | — | 游戏目录 + **最近目录切换**（选完立即生效，不用再点保存）、玩家名、内存、窗口尺寸、全屏、**实例隔离开关（默认开）**、Java 路径与检测、**Java 自动下载**（选大版本 → 立即下载）、下载源（BMCLAPI 镜像 / Mojang 官方，默认镜像）、下载线程、附加 JVM 参数、**账户区**（账号管理 / 微软正版登录 / 第三方皮肤站登录 / 皮肤管理）、**主题配色（PCL 浅蓝 / 暗色 / 亮色 / 深蓝 / 护眼绿，点了立即生效，无需重启）**、显示控制台、一键反馈打包 |

整合包相关（整合包市场 / 导入 `.mrpack`、`.zip` / 导出整合包）在开始页「启动」页签的工具栏里；
拖文件进窗口也能装（`.jar` 进 mods，`.mrpack` / `.zip` 走整合包安装）。

左侧白栏顶部的账户卡显示**游戏头像**（从皮肤站 / Mojang 取皮肤图后裁出脸部，失败则退回首字母），点一下直接切到开始页的**账户页签**：多账号列表、切换、复制离线 UUID、删除、**添加离线账号**、**微软正版登录**、**第三方皮肤站登录**（LittleSkin / MUA / Blessing Skin / 自定义；窗口里不会自动跳浏览器，点「打开认证页面」才打开）、**皮肤管理**（看当前皮肤、上传 PNG、重置、打开衣柜）。

## 界面

仿 PCL2 简洁模式重做的一版布局（默认 `PCL 浅蓝` 配色），全部自绘、无外部 UI 依赖：

- **顶部蓝色渐变栏**（48px）：左侧 `M` 圆角徽标 + 名称；正中间一排**胶囊导航**（开始 / 下载 / 设置），选中项是白底蓝字实心胶囊，悬停是半透明白；右侧是**账户胶囊**（头像 + 名字 + `▾`），点开即账号管理。窗口去掉原生标题栏（摘掉 `WS_CAPTION`、保留 `WS_THICKFRAME`），把**最小化 / 最大化 / 关闭**三个按钮画在顶栏最右端，和蓝色导航栏是同一层，不再有「深色标题栏 + 蓝色顶栏」两截；拖动、贴边吸附、双击标题栏最大化、四边八向缩放仍由系统处理（走 `WM_NCLBUTTONDOWN` + `HTCAPTION`），DWM caption 色同时刷成同一个蓝，让残留的 7px 缩放边框看不出来。
- **左侧白栏**（232px）：大头像 + 名字 + 账户类型（微软正版 / 第三方 / 离线），下面是并排的两个按钮「账户」「皮肤」——原来的三行文字入口（游戏目录 / 版本设置 / 皮肤管理）已合并掉。
- **右侧内容区**：浅蓝底（`#EDF4FD`）+ 白色卡片，卡片 1px 淡蓝描边、无阴影；开始页顶部是 PCL 风格的主视觉横幅，三处列表的空态配了等距体素插画。底部原先那行 26px 状态栏已删除，提示改走浮层。
- 窗口默认 **1160×724**，最小 880×560，居中打开。
- 插画资源放在 `assets/ui/`（`hero.png` / `empty-versions.png` / `empty-mods.png` / `empty-search.png`），由 `tools/make_ui_assets.py` 从 `assets/ui/raw/` 的原始出图裁切生成；运行期只用 `tk.PhotoImage` 读 PNG，**不依赖 Pillow**。

## 运行

```bat
cd F:\MCLite
python main.py
```

需要 Python 3.9+（本机为 `G:\python\python.exe`，3.10.9），无需 `pip install` 任何东西。

## 打包成单文件 exe

```bat
cd F:\MCLite
python -m PyInstaller mclite.spec --noconfirm --clean
```

产物：`dist\MCLite.exe`（约 13 MB，双击即用，不弹控制台窗口）。

## 已实测通过

- **版本安装**：`1.20.1` 装进 `G:\.minecraft` —— 66 个文件 + 3575 个资源文件，大部分命中去重，**23.9 秒**完成；`26.3`（5101 个新资源）完整跑通。
- **启动**：自动选中 `Java 21`（1.20.1 需要 17+），classpath / natives / 参数全部正确；原版、Fabric、Forge、NeoForge 四种实例都能进到主菜单（纹理图集加载完成）。
- **Fabric 安装**：`1.20.1 + fabric-loader` → 写版本 JSON + 补库，**3~5 秒**完成。
- **Forge 安装**：`1.20.1 + forge 47.4.28` —— 先按 SHA1 预下载 63 个安装器依赖（Maven Central → BMCLAPI → 原始地址三路回退），再跑官方 installer 的 processor（打补丁），**约 38 秒**安装完成。
- **NeoForge 安装**：`1.20.1 + neoforge 47.1.105` —— 同样流程，**37.7 秒**完成。
- **整合包**：Modrinth 搜 `fabulously optimized` → 96 个结果；下载 `Fabulously.Optimized-5.4.1.mrpack`（59 KB）→ 自动装 `1.20.1` + `fabric 0.14.23` → 解出 27 个覆盖文件 → 下 51 个文件（26.6 MB）→ 生成实例 `Fabulously Optimized`（48 个 mod），**4.4 秒**（原版与大部分库已命中缓存）。
- **实例隔离**：本机已有的 `modpack` 版本（105 个 mod 放在 `versions\modpack\`）被自动识别为隔离实例，启动日志里能看到 `modloading-worker` 加载 mixin、Embeddium / Oculus 生效，游戏正常进到渲染线程。
- **Java 自动下载**：选「Java 17」→ 从 Mojang 拉 `java-runtime-beta 17.0.15`（403 个文件），**33.4 秒**落地 `runtime/java-runtime-beta/17.0.15/`，`java -version` 识别为 17.0.15 64 位。
- **皮肤站**：LittleSkin / Blessing Skin 的 Yggdrasil API 0.1~0.9 秒可达；authlib-injector `1.2.8`（349 KB）自动下载到 `libraries/mclite/authlib-injector/`；登录后启动自动加 `-javaagent`。
- **主题**：PCL 浅蓝（默认）/ 暗色 / 亮色 / 深蓝 / 护眼绿 五套配色，在设置里点一下**立即重建界面生效，不用重启进程**（含 ttk 滚动条、下拉框配色）；五套都做过截图检查。
- **中文搜索**：内置约 120 条常用译名，`小地图` → `minimap`（31 个结果，Xaero's 排前）、`优化` → `optimization`（46 个结果，FerriteCore 排前）、`钠` → `sodium`；搜不到时退回原始关键词。
- **Modrinth**：模组 `sodium`（38 个结果）、资源包 `faithful`（100 个）、光影 `complementary`（18 个）都能搜到并下载；下载 `sodium-fabric-0.5.13+mc1.20.1.jar`（948.8 KB）验证通过。
- **微软登录**：设备码流程（`microsoft.com/link` 输入 8 位代码）→ Xbox Live → XSTS → Minecraft 档案，实测登录到 `qiuqiu__a`，启动时自动带 `user_type=msa` 的正版令牌。
- **多账号**：正版 + 离线 + 皮肤站账号共存，切换后启动自动用对应 UUID（离线账号用自己的 UUID，皮肤/存档不串）。
- **崩溃诊断**：内置 **34 条规则**（OOM / 元空间 / 堆参数不被接受 / JVM 参数错误 / Java 位数、Java 版本太低、缺前置、缺 Fabric API、模组重复、注册冲突、Mixin 注入、OptiFine 与 Sodium 冲突、光影编译、模块冲突、坏 jar、坏存档、资源包格式、显卡驱动 / OpenGL、缺 VC++ 运行库、本机库缺失、文件不完整、磁盘满、权限不足、网络连不上、声音设备等），命中后给中文结论 + 处理建议，并可一键打包反馈。
- **一键反馈**：`MCLite反馈_<时间>.zip` 输出到桌面，内含系统信息、脱敏配置、模组清单（含 SHA1）、最近日志与崩溃报告。
- **存档管理**：自己写了一个极简 NBT 读取器（gzip + 12 种 tag），能读出 `level.dat` 里的世界名与版本；备份成 `世界名_YYYYmmdd_HHMMSS.zip`，恢复时同名世界自动改名（`xxx_恢复`），防 zip-slip。
- **完整性检查**：`modpack` 实例 **3670 个文件全部正常**，秒级返回；缺文件按 客户端 / 库文件 / 资源文件 分组列出，一键修复走同一套镜像 + SHA1 下载器。
- **导出整合包**：`1.20.1` 导出成 `.mrpack`（`modrinth.index.json` + `overrides/`），再导入回来内容一致；`modpack` 实例（105 个 mod）导出成 **151 MB** 的包，279 个条目、**5.7 秒**，加载器自动识别为 `forge 47.3.1`。
- **种子整合包**：把 `mods/xxx.jar` + `config/` 的普通 zip 拖进窗口 → 自动识别为"散装整合包" → 建一个继承当前版本的独立实例，解出全部文件（实测 2 个文件、秒级）。
- **格式识别**：Modrinth（`modrinth.index.json`）、CurseForge（`manifest.json`，解析出 `forge-47.4.28`）、MultiMC（`mmc-pack.json`，解析出 `1.19.2 + fabric 0.15.1`）、纯 Mod jar 四种都识别正确。
- **CurseForge 模组自动下载**（不需要 API Key）：`manifest.json` 里只有 `projectID` + `fileID`，先用镜像 `api.cfwidget.com` 查出该文件的 jar 文件名，再按 `https://edge.forgecdn.net/files/{id/1000}/{id%1000}/{文件名}` 拼直链下载。实测：1 个模组从解析到落盘 **19.8 秒**（含等两个坏项目超时），Fabric API `fabric-api-0.92.12+1.20.1.jar` 2.1 MB 校验通过；查不到的项目会在日志里列出项目号，方便手动补。
- **多游戏目录**：设置里记住最近 8 个 `.minecraft` 目录，下拉即切，可移除。
- **皮肤**：正版账号读 Mojang 会话服材质、皮肤站账号读 Yggdrasil 材质，顶栏账户胶囊与左栏账户卡都显示真实皮肤（实测 `qiuqiu__a` 皮肤 2045 B，0.66 秒取回）；皮肤管理里可上传 64×64 PNG、重置皮肤、打开衣柜。
- **拖拽**：窗口任意位置拖入 `.jar` → 装进当前实例的 mods；拖入 `.zip` / `.mrpack` → 识别格式后弹出安装进度窗。exe 里 `tkinterdnd2` 的 `tkdnd` 数据文件已随包带上（自检 `dnd=true`）。
- **界面响应**：页面切换 0–35 ms（中位 0）、开始页三个页签 1–2 / 40–70 / 60–80 ms（`tools/smoke_page_switch.py`，预算 120 ms）；窗口拉伸时拖动中单帧 **6–7 ms**（原 95.8 ms）、松手到画面跟上 **150–190 ms**（`tools/smoke_resize.py`，预算 300 ms）。做法：顶栏渐变按宽度缓存、拖拽目标按控件路径去重、页面/页签用 `place + lift` 叠层且**未显示的页签 `place_forget`**、容器尺寸变化 **70 ms 防抖**后才让页面换尺寸（拖动全程页面不重排）。最关键的一条：**拖动一开始给当前页拍一张像素快照盖上去，真页面 `place_forget`**（`App._ensure_snapshot`），之后每帧只需画一张图；快照用 `BitBlt` + `GetDIBits` 直接抓屏（`mclite/ui/grab.py`，**不依赖 PIL**，PIL 那条路首次要 713 ms）。⚠ 抓一张 929×701 实测 **260 ms**（和尺寸无关，是本机从桌面 DC 读像素的固定成本，`tools/probe_grab_impl.py` 换 `CreateDIBSection` 也一样），所以快照**只在连着第二个 `<Configure>` 时才拍**（= 用户真的在拖边框）；单发的尺寸跳变（最大化 / 还原 / 换页）拍快照纯属浪费 —— 这一条把 install 页的「松手对齐」从 390–400 ms 直接压到 185 ms。停手 70 ms 后按新尺寸摆回真页面、销毁快照。版本列表只铺 **60 行**（原 400 行 = 2400 个控件），切筛选从 410 ms 回到 1 ms 级。
- **拖动不出残影**（两处根因都已修）：
  1. 顶栏是 Canvas 手绘的，宽度一变原来只重铺渐变、**不清前景**，每改一次宽度就多攒 14 个 item（8 档后「MCLite / 开始 下载 设置」叠了 6 份）。现在宽度变化时 `delete("all")` 整块重来，前景统一挂 `fg` 标签做局部刷新，`tools/smoke_topbar_ghost.py` 断言连续改宽 8 档 item 恒为 175。
  2. **v1.7.1/1.7.2 的「冻结整窗重绘」方案是错的，v1.7.3 已全部拆除**。`LockWindowUpdate` + `WM_SETREDRAW(0)` 能把帧成本压到 3 ms，但画面会坏：Windows 把最后一帧**拉伸**铺满新窗口（顶栏被拉成一条横带、文字糊掉），解冻后正文还常整片空白——用户看到的「残影」正是这个。现在改用上面的像素快照方案，`tools/smoke_snapshot.py` 对三页做逐像素比对，拖动中画面与拖动前差异 **0.00%**，窗口变大时新露出的是容器底色（100% 命中，无拉伸）。

- **小窗口不裁控件**：窗口最小 880×560，往下压到这条线时三页都不会有按钮被切一半、文字被截断（`tools/smoke_small_window.py`，判据是「控件想要的宽度 > 实际拿到的宽度 + 2px」，880×560 / 1000×640 / 1160×724 三档都是 0 个）。做法：左栏宽度按页面宽度动态算（`mclite/ui/responsive.py` 的 `left_width()`，380 → 最窄 232/240），工具条和按钮行换成能自动换行的 `FlowRow`，版本名等长文本按剩余宽度降字号 + `wraplength` 换行，右栏（版本信息 / 玩家名 / 内存 / 日志）整体塞进 `ScrollFrame` 而**启动按钮钉在右下角**——低窗口时只有右栏内容滚动，启动按钮永远可见。另外 `Canvas` / `Text` 都显式写了 `width=1`：Tk 默认给 `Text` 请求 80 字符宽（≈496 px）、`Canvas` 请求 378 px，会把同一行的兄弟控件挤出窗口。

## 说明

- 下载源默认走 **BMCLAPI 镜像**（国内直连 Mojang 基本拉不动）；切到「Mojang 官方」后是另一套前缀，两条路都失败时自动回退对方。
- 下载支持 **SHA1 校验 + `.part` 断点续传**：中断后重来会从中断处续上，不重下已完成的文件。
- 登录默认**离线模式**（`OfflinePlayer:<名字>` 生成 UUID）；登录微软账户后自动改用正版令牌，令牌过期自动刷新；登录皮肤站后启动会注入 authlib-injector。
- **实例隔离**：默认**开启**（每个版本用 `<游戏目录>\versions\<版本>\` 当自己的 `.minecraft`，各自独立的 mods / 存档 / 配置 / 日志）。想要 PCL 那种「所有版本共用一个 mods」的老习惯，到设置里关掉即可。**整合包永远隔离**，而且启动器会自动识别「版本目录里已经有 mods / 存档 / 配置」的旧实例（PCL、HMCL 留下的那种），不会让它们掉 mod。
- Minecraft **1.6 及更早**游戏版本需要的 `assets/virtual/legacy` 资源展开尚未实现，1.7+ 不受影响。
- 游戏崩溃 / 报错看 `<游戏目录>\logs\mclite-<版本>-latest.log`。

## 还没做的

- 启动器自更新
- Minecraft 1.6 及更早版本的 legacy assets 展开
- CurseForge 个别项目拿不到文件列表时（镜像没收录 / 网络掐断），对应模组仍需手动补

## 命令行

```bat
MCLite.exe --page install     :: 直接打开某页（home / install / settings；mods 会打开开始页的模组页签）
```

## 配置位置

`%APPDATA%\MCLite\config.json` —— 删掉它就恢复默认设置（首次启动会自动猜一个 `.minecraft` 目录）。
