# -*- mode: python ; coding: utf-8 -*-
"""VexRush 的 PyInstaller 打包配置（单文件 exe）。"""

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets/fonts/ChillRoundM.otf', 'assets/fonts'),
        ('assets/fonts/LICENSE-ChillRound.txt', 'assets/fonts'),
    ],
    hiddenimports=[
        'pynput.keyboard._win32',
        'pynput.keyboard._darwin',
        'pynput.mouse._win32',
        'win32timezone',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'unittest', 'pydoc_data', 'test',
        'PyQt5.QtQml', 'PyQt5.QtQuick', 'PyQt5.QtQuickWidgets', 'PyQt5.QtQuick3D',
        'PyQt5.QtWebEngine', 'PyQt5.QtWebEngineCore', 'PyQt5.QtWebEngineWidgets',
        'PyQt5.QtMultimedia', 'PyQt5.QtMultimediaWidgets', 'PyQt5.QtSql', 'PyQt5.QtTest',
        'PyQt5.QtSvg', 'PyQt5.QtOpenGL', 'PyQt5.QtDBus', 'PyQt5.QtNetwork',
        'PyQt5.QtXml', 'PyQt5.QtPrintSupport', 'PyQt5.QtDesigner', 'PyQt5.QtBluetooth',
        'PyQt5.QtNfc', 'PyQt5.QtPositioning', 'PyQt5.QtSerialPort', 'PyQt5.QtWebSockets',
        'PySide6', 'PyQt6', 'numpy', 'PIL', 'matplotlib', 'pandas', 'scipy',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
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
    name='VexRush',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',
    version='version_info.txt',
)
