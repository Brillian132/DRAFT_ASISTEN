# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = [('D:/asisten/backend-python-eksperimen/ffmpeg.exe', '.'), ('D:/asisten/backend-python-eksperimen/ffprobe.exe', '.')]
hiddenimports = ['engineio.async_drivers.threading', 'simple_websocket', 'pyttsx3.drivers', 'pyttsx3.drivers.sapi5', 'pythoncom', 'win32com.client', 'requests', 'urllib3', 'charset_normalizer', 'idna', 'certifi', 'pyaudio', 'pydub']
tmp_ret = collect_all('speech_recognition')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['../server.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    [],
    exclude_binaries=True,
    name='asisten-server-test',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='asisten-server-test',
)
