"""把改好的 PCL 启动器打包一份放到桌面。

打包内容（PCL 的目录约定：Setup.ini 放在 exe 同级的 PCL\ 里）：
    PCL 2.14.0.0/
        Plain Craft Launcher 2.exe   官方 2.14.0.0（还带 MC 下载功能的那版）
        PCL/Setup.ini                含 SystemSystemUpdate:3 -> 关闭自动更新
        使用说明.txt
"""

from __future__ import annotations

import hashlib
import shutil
import zipfile
from pathlib import Path

DESKTOP = Path.home() / "Desktop"
SRC_EXE = Path(r"G:\mc\versions\pcl.exe")
SRC_INI = Path(r"G:\mc\versions\PCL\Setup.ini")
STAGE_ROOT = Path(r"F:\MCLite\build\pcl_pack")
FOLDER = "PCL 2.14.0.0"
ZIP_NAME = "PCL-2.14.0.0-修改版.zip"

EXPECT_SHA256 = "5582952DED3B443503F66C23B810802BD20F1A3E847B54D9E09653A825859A36"

README = """PCL 2.14.0.0 —— 已解除限制 / 已关闭自动更新
================================================

这个包里放的是改好的 Plain Craft Launcher（简称 PCL）启动器，
解压后直接双击「Plain Craft Launcher 2.exe」就能用。


一、这一版改了什么
----------------
1) 换回了 2.14.0.0（官方正式版）。
   PCL 从 2.13.1.1 之后的版本开始，按上游的公告「不再提供 MC 下载功能」，
   启动器里下载 Minecraft 的入口被删掉了。2.14.0.0 是删除之前最后一版
   还带完整下载功能的正式版，所以换回它，下载功能就回来了。
   实测能正常拉取 Mojang / BMCLAPI 的版本清单并安装、启动。

2) 关闭了自动更新（Setup.ini 里 SystemSystemUpdate:3）。
   自动更新一旦跑起来，会把你升级回「没有下载功能」的新版本。
   所以这一版把更新关掉了，请不要再手动点「检查更新」。


二、为什么 Setup.ini 要放在 PCL 文件夹里
--------------------------------------
PCL 把配置存放在 exe 同级的「PCL」文件夹里（Sources.Normal 存 Setup.ini，
Sources.Registry 存注册表 HKCU\\Software\\PCL）。
所以包里的结构是：

    PCL 2.14.0.0\\
        Plain Craft Launcher 2.exe
        PCL\\
            Setup.ini        <-- 关闭自动更新的配置

把这个文件夹整个解压出来、直接运行 exe，就会读到上面的 Setup.ini。
如果你只把 exe 单独拷走（不带 PCL 文件夹），它是能跑，
但自动更新会恢复默认（= 重新开启），下次就可能被升级掉。
换电脑、换目录时请把 PCL 文件夹一起带着。


三、校验
--------
Plain Craft Launcher 2.exe
    大小    5,989,376 字节
    版本    2.14.0.0
    SHA256  5582952DED3B443503F66C23B810802BD20F1A3E847B54D9E09653A825859A36

想自己核对，可以在资源管理器里对着 exe 右键 -> 属性 -> 数字签名/详细信息，
或者在 PowerShell 里执行：

    Get-FileHash "Plain Craft Launcher 2.exe" -Algorithm SHA256

算出来的值应该和上面那一长串完全一致。


四、需要注意
----------
- 用的是官方 2.14.0.0，没有改过 exe 本体（哈希与官方发布包一致），
  所以不是破解版，也没有加任何东西。
- 「不提供下载」这件事在上游是服务端公告驱动的：PCL 每次启动会去拉
  notice.json，看到公告就会提示你更新。这一版因为关掉了更新，
  公告不会再把你升级走；但如果哪天公告改成强制行为，可能还会弹提示。
- 需要 Java 才能启动游戏。PCL 自带的 Java 下载功能在这一版是好的，
  也可以自己指定已装的 Java。
- 只建议自用或给熟人。别拿去二次发布——PCL 有它自己的授权条款。
"""


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def main() -> int:
    for p in (SRC_EXE, SRC_INI):
        if not p.is_file():
            print(f"缺少源文件：{p}")
            return 1

    digest = sha256_of(SRC_EXE)
    print(f"源 exe  {SRC_EXE}")
    print(f"  大小    {SRC_EXE.stat().st_size} 字节")
    print(f"  SHA256  {digest}")
    if digest != EXPECT_SHA256:
        print(f"哈希与预期不符！预期 {EXPECT_SHA256}")
        return 1
    print("  哈希与官方 2.14.0.0 一致")

    # 组装
    if STAGE_ROOT.exists():
        shutil.rmtree(STAGE_ROOT)
    stage = STAGE_ROOT / FOLDER
    (stage / "PCL").mkdir(parents=True)

    exe_dst = stage / "Plain Craft Launcher 2.exe"
    shutil.copy2(SRC_EXE, exe_dst)
    # 二进制原样复制，不转码（Setup.ini 是无 BOM 的 UTF-8/CRLF）
    shutil.copy2(SRC_INI, stage / "PCL" / "Setup.ini")

    readme = stage / "使用说明.txt"
    readme.write_text(README, encoding="utf-8", newline="\r\n")

    if sha256_of(exe_dst) != digest:
        print("复制后哈希变化，中止")
        return 1

    # 打包（zip 内部用正斜杠，中文名写 UTF-8 标志位）
    DESKTOP.mkdir(parents=True, exist_ok=True)
    zip_path = DESKTOP / ZIP_NAME
    if zip_path.exists():
        zip_path.unlink()

    files = [
        (exe_dst, f"{FOLDER}/Plain Craft Launcher 2.exe"),
        (stage / "PCL" / "Setup.ini", f"{FOLDER}/PCL/Setup.ini"),
        (readme, f"{FOLDER}/使用说明.txt"),
    ]
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path, arc in files:
            zf.write(path, arc)

    size = zip_path.stat().st_size
    print(f"\n已生成 {zip_path}")
    print(f"  大小    {size} 字节 ({size / 1048576:.2f} MB)")
    print(f"  SHA256  {sha256_of(zip_path)}")

    # 自检：重新打开确认条目与内容
    with zipfile.ZipFile(zip_path) as zf:
        bad = zf.testzip()
        print(f"  自检    {'OK' if bad is None else '损坏 ' + str(bad)}")
        for info in zf.infolist():
            print(f"    {info.file_size:>9}  {info.filename}")
        ini = zf.read(f"{FOLDER}/PCL/Setup.ini").decode("utf-8")
    if "SystemSystemUpdate:3" not in ini:
        print("Setup.ini 里没有 SystemSystemUpdate:3！")
        return 1
    print("  Setup.ini 已确认含 SystemSystemUpdate:3（关闭自动更新）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
