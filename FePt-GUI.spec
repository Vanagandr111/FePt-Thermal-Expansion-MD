# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['gui/server.py'],
    pathex=['scripts'],
    binaries=[],
    datas=[('gui/static', 'gui/static'), ('scripts', 'scripts'),
           ('data/hints_base.json', 'data')],
    hiddenimports=['tray', 'pystray', 'pystray._win32',
                   'PIL', 'PIL.Image', 'PIL.ImageDraw',
                   'openpyxl', 'openpyxl.drawing.image',
                   'openpyxl.styles', 'openpyxl.utils'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'mace', 'ase', 'scipy', 'pandas', 'matplotlib'],
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
    name='FePt-GUI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
