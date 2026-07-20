# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for DragonMIDI - Windows.

No icon yet - drop an assets/dragonmidi.ico in and add `icon='assets/dragonmidi.ico'`
to the EXE() call below once one exists (see StagehandClient-win.spec for the pattern).
"""

block_cipher = None

a = Analysis(
    ['pyinstaller_entry.py'],
    pathex=[],
    binaries=[],
    datas=[],
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
)
