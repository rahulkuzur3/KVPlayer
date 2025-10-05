# -*- mode: python ; coding: utf-8 -*-

# This is the definitive, corrected .spec file that uses universal
# path detection for all dependencies.

import sys
from pathlib import Path
from kivy_deps import sdl2, glew

# --- THE DEFINITIVE FIX for the 'libs' FileNotFoundError ---
import ffpyplayer
# This is the correct, universal way to get the ffpyplayer package directory
ffpyplayer_dir = Path(ffpyplayer.__file__).parent


# --- Main Configuration ---
a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('kvplayer.kv', '.'),
        ('Font Awesome 7 Free-Solid-900.otf', '.'),
    ],
    hiddenimports=[
        'ffpyplayer',
        'plyer.platforms.win.filechooser',
        'plyer.platforms.macosx.filechooser',
        'plyer.platforms.linux.filechooser',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# --- Collect all necessary DLLs/shared libraries ---
a.binaries = a.binaries + Tree(sdl2.dep_bins[0], prefix='sdl2')
a.binaries = a.binaries + Tree(glew.dep_bins[0], prefix='glew')
# Use the corrected, universal path for the ffpyplayer package
a.binaries = a.binaries + Tree(ffpyplayer_dir, prefix='ffpyplayer')

pyz = PYZ(a.pure, a.zipped_data, cipher=None)


# --- Platform-Specific Executable Settings ---

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='KVPlayer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico'
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='KVPlayer',
)

# On macOS, this will be used to create the .app bundle
app = BUNDLE(
    coll,
    name='KVPlayer.app',
    icon='icon.icns',
    bundle_identifier='com.yourname.kvplayer',
)