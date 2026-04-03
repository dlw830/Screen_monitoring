# -*- mode: python ; coding: utf-8 -*-
"""
LanScreenMonitor V1 - PyInstaller 打包配置
使用命令: pyinstaller LanScreenMonitor.spec
"""

import os

block_cipher = None

# 项目根目录
PROJECT_DIR = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    [os.path.join(PROJECT_DIR, 'app.py')],
    pathex=[PROJECT_DIR],
    binaries=[],
    datas=[
        # 打包 web 静态资源
        (os.path.join(PROJECT_DIR, 'web'), 'web'),
    ],
    hiddenimports=[
        'aiortc',
        'aiortc.contrib.media',
        'aiohttp',
        'av',
        'cv2',
        'mss',
        'mss.windows',
        'psutil',
        'qrcode',
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'tkinter',
        'numpy',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'scipy',
        'pandas',
        'IPython',
        'jupyter',
        'notebook',
        'pytest',
        'sphinx',
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
    [],
    exclude_binaries=True,
    name='LanScreenMonitor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # 保留控制台输出（支持热键）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # 版本信息
    version='file_version_info.txt' if os.path.exists(os.path.join(PROJECT_DIR, 'file_version_info.txt')) else None,
    icon=None,  # 可选：添加 .ico 图标
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='LanScreenMonitor',
)
