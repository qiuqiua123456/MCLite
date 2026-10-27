# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：单文件、无控制台、带图标。

用法：python -m PyInstaller mclite.spec --noconfirm
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH)

block_cipher = None

# tkinterdnd2 的 tkdnd 是一堆 .tcl / .dll，必须作为数据文件带上，
# 否则打包后的 exe 里拖拽会静默失效（TkinterDnD._require 找不到包）。
dnd_data = collect_data_files("tkinterdnd2")

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "assets" / "icon.ico"), "assets"),
        (str(ROOT / "assets" / "ui"), "assets/ui"),
    ] + dnd_data,
    hiddenimports=[
        "mclite.ui.page_home",
        "mclite.ui.page_install",
        "mclite.ui.page_mods",
        "mclite.ui.page_settings",
        "mclite.ui.mod_dialog",
        "mclite.ui.loader_dialog",
        "mclite.ui.ms_login",
        "mclite.ui.account_dialog",
        "mclite.ui.crash_dialog",
        "mclite.ui.pack_dialog",
        "mclite.ui.skin_dialog",
        "mclite.ui.skin_mgr_dialog",
        "mclite.ui.world_dialog",
        "mclite.ui.verify_dialog",
        "mclite.accounts",
        "mclite.crash",
        "mclite.feedback",
        "mclite.instances",
        "mclite.javaauto",
        "mclite.modpack",
        "mclite.skin_sites",
        "mclite.packdetect",
        "mclite.curseforge",
        "mclite.worlds",
        "mclite.verify",
        "mclite.exportpack",
        "mclite.skins",
        "mclite.cnsearch",
        "tkinterdnd2",
        "tkinterdnd2.TkinterDnD",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 只排掉体积大且完全没用到的第三方库；标准库一律不动
        # （urllib.request 依赖 email，排掉 email 会直接 ImportError）
        "numpy", "pandas", "matplotlib", "scipy",
        "pytest", "setuptools", "pip", "wheel",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="MCLite",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "icon.ico"),
)
