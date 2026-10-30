# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
# PyInstaller recipe of the Qt window. Build with:  pyinstaller steamcase-qt.spec
import os, sys

# keep in step with qtui/assets.py (a test compares them)
ASSETS = ["frame.png", "family_corner.png", "completion_overlay.png", "default_art.png", "icon.png", "discord.png", "halloween_overlay.png"]
# assets/version.txt only exists in release builds (the workflow writes the tag into it); source runs report "dev"
if os.path.exists("assets/version.txt"):
    ASSETS.append("version.txt")
a = Analysis(["qtui/__main__.py"], pathex=["."], datas=[("qtui/qml", "qtui/qml")] + [("assets/" + n, "assets") for n in ASSETS],
             excludes=["numpy", "matplotlib", "scipy", "pandas", "tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtCharts"])
pyz = PYZ(a.pure)

if sys.platform == "darwin":                       # macOS: folder-based .app (single-file .app is discouraged)
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="SteamCaseCoversQt", console=False)
    coll = COLLECT(exe, a.binaries, a.datas, name="SteamCaseCoversQt")
    app = BUNDLE(coll, name="SteamCaseCoversQt.app", icon="assets/icon.icns", bundle_identifier="com.github.diegobergonsi.steamcasecovers.qt")
else:                                              # Windows and Linux: one file
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="SteamCaseCoversQt", console=False,
              icon="assets/icon.ico" if sys.platform.startswith("win") else None)
