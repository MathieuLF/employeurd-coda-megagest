# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path


ROOT = Path(SPECPATH).resolve().parents[1]
APP_NAME = os.environ.get("EMG_APP_NAME", "EmployeurD-MegaGest")

a = Analysis(
    [str(ROOT / 'src' / 'employeurd_megagest' / 'gui_entry.py')],
    pathex=[str(ROOT / 'src')],
    binaries=[],
    datas=[(str(ROOT / 'config'), 'config')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    manifest=str(ROOT / 'packaging' / 'windows' / 'EmployeurD-MegaGest.manifest'),
)
