# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import os

from PyInstaller.utils.hooks import collect_all, collect_submodules


ROOT = Path(SPECPATH)
MODE = os.environ.get("MATHMASTER_BUILD_MODE", "onedir").lower()
DEBUG = os.environ.get("MATHMASTER_DEBUG", "0") == "1"
if MODE not in {"onedir", "onefile"}:
    raise ValueError("MATHMASTER_BUILD_MODE must be 'onedir' or 'onefile'.")

datas = []
for relative in (
    "assets/icons",
    "assets/fonts",
    "data/mathematics",
    "data/exams",
    "data/manifests",
):
    source = ROOT / relative
    if source.is_dir():
        datas.append((str(source), relative))

binaries = []
hiddenimports = []
for package in (
    "customtkinter",
    "sympy",
    "matplotlib",
    "bcrypt",
    "cryptography",
    "keyring",
    "websocket",
):
    package_datas, package_binaries, package_hiddenimports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports
hiddenimports += collect_submodules("matplotlib.backends")
hiddenimports += [
    "unittest",
    "unittest.case",
    "unittest.loader",
    "unittest.main",
    "unittest.result",
    "unittest.runner",
    "unittest.signals",
    "unittest.suite",
    "unittest.util",
    "unittest.async_case",
]

icon_path = ROOT / "assets" / "icons" / "mathmaster.ico"
icon = str(icon_path) if icon_path.is_file() else None
a = Analysis(
    ["main.py"],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

if MODE == "onefile":
    EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="MathMaster",
        debug=DEBUG,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=DEBUG,
        disable_windowed_traceback=not DEBUG,
        icon=icon,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="MathMaster",
        debug=DEBUG,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=DEBUG,
        disable_windowed_traceback=not DEBUG,
        icon=icon,
    )
    COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name="MathMaster",
    )

