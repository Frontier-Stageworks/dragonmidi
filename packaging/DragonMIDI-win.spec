# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for DragonMIDI - Windows.
"""

import os

block_cipher = None
# SPECPATH is injected by PyInstaller as this spec file's own directory.
# Explicit, since dragonmidi is an editable install and PyInstaller's static
# analysis does not reliably follow the editable-install redirect on its own -
# without this, the build succeeds but the frozen app fails at runtime with
# "No module named 'dragonmidi'".
REPO_ROOT = os.path.join(SPECPATH, "..")

a = Analysis(
    ['pyinstaller_entry.py'],
    pathex=[REPO_ROOT],
    binaries=[],
    datas=[
        (os.path.join(REPO_ROOT, 'assets/dragonmidi.ico'), '.'),
        (os.path.join(REPO_ROOT, 'assets/dragonmidi.png'), '.'),
    ],
    hiddenimports=[
        'mido.backends.rtmidi',
        'pynput.keyboard._win32',
        'pynput.mouse._win32',
    ],
    collect_all=['PySide6', 'websockets'],
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
    name='DragonMIDI',
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
    icon=os.path.join(REPO_ROOT, 'assets/dragonmidi.ico'),
)
