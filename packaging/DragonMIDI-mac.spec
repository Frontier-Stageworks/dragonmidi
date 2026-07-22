# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for DragonMIDI - macOS .app bundle.

Icon: assets/dragonmidi.icns (generated from assets/dragonmidi.png by the CI
      workflow; not committed - create locally with the iconutil steps in
      .github/workflows/build-mac.yml if building manually).

No Info.plist usage-description keys are needed for the keystroke output path
(macOS Accessibility access is a TCC prompt tied to the app appearing in
System Settings > Privacy & Security > Accessibility, not an Info.plist key).
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
        (os.path.join(REPO_ROOT, 'assets/dragonmidi.png'), '.'),
        (os.path.join(REPO_ROOT, 'assets/dragonmidi.icns'), '.'),
        (os.path.join(REPO_ROOT, 'dragonmidi/controllers'), 'dragonmidi/controllers'),
    ],
    hiddenimports=[
        'mido.backends.rtmidi',
        'pynput.keyboard._darwin',
        'pynput.mouse._darwin',
    ],
    collect_all=['PySide6', 'websockets'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DragonMIDI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='DragonMIDI',
)

app = BUNDLE(
    coll,
    name='DragonMIDI.app',
    icon=os.path.join(REPO_ROOT, 'assets/dragonmidi.icns'),
    bundle_identifier='com.frontierstageworks.dragonmidi',
    info_plist={
        'NSHighResolutionCapable': True,
        'CFBundleShortVersionString': '0.1.0',
        'LSMinimumSystemVersion': '12.0',
    },
)
