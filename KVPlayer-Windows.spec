# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

# This path is generated from your 'pip show kivy' output.
kivy_hooks_path = 'C:\\Users\\Labib\\AppData\\Local\\Programs\\Python\\Python311\\Lib\\site-packages\\kivy\\tools\\pyinstaller\\hooks'

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('kvplayer.kv', '.'),
        ('font.otf', '.'),
        ('icon.png', '.')
    ],
    hiddenimports=['plyer.platforms.win.filechooser'],
    hookspath=[kivy_hooks_path],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False
)
pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher
)

# The EXE block now defines the final one-file bundle.
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,   # <-- Add binaries here
    a.zipfiles,   # <-- Add zipfiles here
    a.datas,      # <-- Add datas here
    [],
    name='KVPlayer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico'
)

# --- The COLLECT block has been removed ---
# coll = COLLECT(
#     exe,
#     a.binaries,
#     a.zipfiles,
#     a.datas,
#     strip=False,
#     upx=True,
#     upx_exclude=[],
#     name='KVPlayer'
# )
