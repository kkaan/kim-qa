# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

a = Analysis(
    ['kim_server_entry.py'],
    pathex=[],
    binaries=[],
    # Built frontend served by the app (resolved via sys._MEIPASS/webapp/dist).
    datas=[('../webapp/dist', 'webapp/dist')],
    hiddenimports=[
        'uvicorn.logging',
        'uvicorn.loops.auto',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan.on',
        # The uv editable install routes kim_qa through a PEP 660 finder that
        # PyInstaller cannot trace statically, so every submodule must be
        # forced in; collect at build time so new modules are never missed.
        *collect_submodules('kim_qa'),
    ],
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='KIM-QA-Server',
    debug=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=True,          # server logs are useful; closing the window stops it
)
