"""PyInstaller entry point.

`dragonmidi/__main__.py` uses a package-relative import (`from .app import run`),
which fails when PyInstaller's Analysis treats it as a standalone top-level
script rather than a package module. This wrapper imports absolutely instead,
avoiding that - see DragonMIDI-win.spec / DragonMIDI-mac.spec.
"""
from dragonmidi.app import run

if __name__ == "__main__":
    run()
