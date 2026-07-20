# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for DragonMIDI - macOS .app bundle.

No icon yet. To add one: drop a source PNG in assets/, generate an .icns with
`sips` (resize to each required size) and `iconutil -c icns` (assemble the
.iconset into the .icns), then set icon='assets/dragonmidi.icns' below and in
the BUNDLE() call.

No Info.plist usage-description keys are needed for the keystroke output path
(macOS Accessibility access is a TCC prompt tied to the app appearing in
System Settings > Privacy & Security > Accessibility, not an Info.plist key).
"""

block_cipher = None

a = Analysis(
    ['pyinstaller_entry.py'],
    pathex=[],
    binaries=[],
    datas=[],
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
    icon=None,
    bundle_identifier='com.frontierstageworks.dragonmidi',
    info_plist={
        'NSHighResolutionCapable': True,
        'CFBundleShortVersionString': '0.1.0',
        'LSMinimumSystemVersion': '12.0',
    },
)
