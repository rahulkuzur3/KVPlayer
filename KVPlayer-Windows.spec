# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

# --- IMPORTANT ---
# This path is generated from your 'pip show kivy' output.
kivy_hooks_path = 'C:\\Users\\Labib\\AppData\\Local\\Programs\\Python\\Python311\\Lib\\site-packages\\kivy\\tools\\pyinstaller\\hooks' # <--- THIS IS YOUR PATH

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
    hookspath=[kivy_hooks_path],  # <--- Use the path here
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
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico' # It's best to use a .ico file for Windows icons
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='KVPlayer'
)