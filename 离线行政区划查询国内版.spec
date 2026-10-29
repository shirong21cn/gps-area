# -*- mode: python ; coding: utf-8 -*-
# 国内版：只打包中国数据（counties.js / provinces.js），不含 world_admin*.js


a = Analysis(
    ['launcher_cn.py'],
    pathex=[],
    binaries=[],
    datas=[('data/counties.js', 'data'), ('data/provinces.js', 'data'),
           ('offline_map_cn.html', '.')],
    hiddenimports=[],
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
    name='离线gps行政区划查询（国内版）',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='version_info_cn.txt',
)
