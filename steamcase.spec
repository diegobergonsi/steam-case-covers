# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
# PyInstaller recipe. Build with:  pyinstaller steamcase.spec
import sys

a = Analysis(["gui.py"], datas=[("assets/frame.png", "assets"), ("assets/icon.png", "assets")], excludes=["numpy", "matplotlib", "scipy", "pandas"])
pyz = PYZ(a.pure)

if sys.platform == "darwin":                       # macOS: folder-based .app (single-file .app is discouraged)
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="SteamCaseCovers", console=False)
    coll = COLLECT(exe, a.binaries, a.datas, name="SteamCaseCovers")
    app = BUNDLE(coll, name="SteamCaseCovers.app", icon="assets/icon.icns", bundle_identifier="com.github.diegobergonsi.steamcasecovers")
else:                                              # Windows and Linux: one file
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="SteamCaseCovers", console=False,
              icon="assets/icon.ico" if sys.platform.startswith("win") else None)
