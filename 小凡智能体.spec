# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['server.py'],
    pathex=[],
    binaries=[],
    datas=[('index.html', '.'), ('qrcode.js', '.'), ('official_skills.js', '.'), ('marked.min.js', '.'), ('purify.min.js', '.'), ('html-docx.js', '.'), ('manifest.json', '.'), ('sw.js', '.'), ('icons', 'icons'), ('wallpapers', 'wallpapers')],
    hiddenimports=['trafilatura'],
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
    name='小凡智能体',
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
    icon=['icon.ico'],
)
