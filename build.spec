# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['app/main.py'],
    pathex=[r'D:\project\RPA'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'app.config',
        'app.storage.database',
        'app.core.tts_service',
        'app.wecom_bot',
        'app.wecom_bot.config',
        'pymysql',
        'openpyxl',
        'xlrd',
        'cryptography',
        'cryptography.fernet',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='RPA管理系统',
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
)
