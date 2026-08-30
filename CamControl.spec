# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys

ROOT = Path(SPECPATH)

a = Analysis(
    [str(ROOT / 'src' / 'camera_bridge' / 'main.py')],
    pathex=[str(ROOT / 'src')],
    binaries=[
        (str(ROOT / 'tools' / 'go2rtc.exe'), 'tools'),
    ],
    datas=[
        (str(ROOT / 'camera-platform' / 'dashboard.html'), 'camera-platform'),
        (str(ROOT / 'camera-platform' / 'static'), 'camera-platform/static'),
        (str(ROOT / 'tools' / 'go2rtc.yaml'), 'tools'),
        (str(ROOT / 'cameras.json'), '.'),
    ],
    hiddenimports=[
        'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto',
        'uvicorn.protocols', 'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan',
        'uvicorn.lifespan.on', 'fastapi', 'camera_bridge',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'pandas', 'PIL', 'tkinter',
              'cv2', 'opencv', 'azure'],  # exclude large unused deps
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas,
    [],
    name='CamControl',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,          # shows startup log; change to False for silent
    icon=None,
    onefile=True,
)
