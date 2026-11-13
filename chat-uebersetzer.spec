# -*- mode: python ; coding: utf-8 -*-

from pathlib import PureWindowsPath

from comtypes.client import GetModule


# Generate the Windows UI Automation bindings in a fresh build environment.
GetModule("UIAutomationCore.dll")

a = Analysis(
    ["chat_uebersetzer.py"],
    hiddenimports=["comtypes.gen.UIAutomationClient"],
    datas=[("LICENSE", "."), ("third-party", "third-party"), ("apply_update.ps1", ".")],
)

# The Microsoft runtime is installed separately using Microsoft's redistributable.
a.binaries = [
    entry for entry in a.binaries
    if PureWindowsPath(entry[0]).name.casefold() not in ("ucrtbase.dll", "msvcp140.dll")
    and not PureWindowsPath(entry[0]).name.casefold().startswith(("vcruntime", "api-ms-win-"))
]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="Chat-Uebersetzer-win-x64",
    console=False,
    upx=False,
)
