# backupman.spec - PyInstaller build specification
# Run: pyinstaller backupman.spec

import os
from pathlib import Path

block_cipher = None

ROOT = Path(SPECPATH)

a = Analysis(
    [str(ROOT / 'main.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # Bundle the entire frontend directory
        (str(ROOT / 'frontend'), 'frontend'),
    ],
    hiddenimports=[
        'apscheduler',
        'apscheduler.schedulers.background',
        'apscheduler.triggers.cron',
        'apscheduler.triggers.interval',
        'apscheduler.triggers.date',
        'flask',
        'flask_cors',
        'werkzeug',
        'werkzeug.serving',
        'sqlite3',
        'win32api',
        'win32con',
    ],
    hookspath=[],
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
    name='Backupman',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # No console window - background app
    icon=str(ROOT / 'icon.ico'),
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
