# -*- mode: python ; coding: utf-8 -*-

hiddenimports = []
datas = [
    ("../assets/logo.png", "assets"),
    ("../assets/logo-64.png", "assets"),
    ("../assets/logo.ico", "assets"),
    ("../assets/fonts/NotoSansCJK-Regular.ttc", "assets/fonts"),
    ("../assets/fonts/OFL-1.1.txt", "licenses"),
    ("../assets/models/small", "assets/models/small"),
    ("../assets/tools/ffmpeg.exe", "assets/tools"),
    ("../assets/tools/ffprobe.exe", "assets/tools"),
    ("../LICENSE", "licenses"),
    ("../THIRD_PARTY_NOTICES.md", "licenses"),
    ("licenses/FFmpeg-NOTICE.txt", "licenses"),
    ("licenses/WHISPER-MODEL-NOTICE.txt", "licenses"),
]
a = Analysis(
    ["gui_launcher.py"],
    pathex=["../src"],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["torch", "tensorflow"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SyncVideo-Audio",
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
    icon="../assets/logo.ico",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SyncVideo-Audio",
)
