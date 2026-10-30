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
# Drop what the window never uses: other Qt styles and dialogs, the GTK theme plugin and the system libraries only it pulls in (GTK, cairo, pango, a second ICU),
# plugins for screens without a desktop, unused image formats. Measured: 113.8 MB -> 73.2 MB, same window. tests/test_qtui.py checks the list against what the window needs.
BLOCK = ["platformthemes/libqgtk3", "egldeviceintegrations", "plugins/generic", "networkinformation", "plugins/tls", "qmltooling", "iconengines",
         "libqeglfs", "libqlinuxfb", "libqminimal", "libqvkkhrdisplay", "libqvnc",
         "imageformats/libqgif", "imageformats/libqicns", "imageformats/libqico", "imageformats/libqsvg", "imageformats/libqtga", "imageformats/libqtiff", "imageformats/libqwbmp",
         "QtQuick/Controls/FluentWinUI3", "QtQuick/Controls/Fusion", "QtQuick/Controls/Imagine", "QtQuick/Controls/Material", "QtQuick/Controls/Universal",
         "QtQuick/Controls/Native", "QtQuick/Controls/designer", "QtQuick/Particles", "QtTest", "qml/QtWayland",
         "libQt6QuickControls2Imagine", "libQt6QuickControls2FluentWinUI3", "libQt6QuickControls2Material", "libQt6QuickControls2Universal", "libQt6QuickControls2Fusion",
         "libQt6QuickControls2Native", "libQt6LabsStyleKit", "libQt6QuickParticles", "libQt6QuickTest", "libQt6Test", "libQt6WaylandCompositor",
         "libgtk-3", "libgdk-3", "libgdk_pixbuf", "libatk", "libatspi", "libcairo", "libpango", "libglycin", "libcloudproviders", "libjson-glib", "libtinysparql", "libepoxy",
         "libicudata.so.78", "libicuuc.so.78", "libQt6Widgets", "libQt6Svg", "libavif"]
a.binaries = [e for e in a.binaries if not any(b in e[0] for b in BLOCK)]
a.datas = [e for e in a.datas if not any(b in e[0] for b in BLOCK)]
pyz = PYZ(a.pure)

if sys.platform == "darwin":                       # macOS: folder-based .app (single-file .app is discouraged)
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="SteamCaseCoversQt", console=False)
    coll = COLLECT(exe, a.binaries, a.datas, name="SteamCaseCoversQt")
    app = BUNDLE(coll, name="SteamCaseCoversQt.app", icon="assets/icon.icns", bundle_identifier="com.github.diegobergonsi.steamcasecovers.qt")
else:                                              # Windows and Linux: one file
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="SteamCaseCoversQt", console=False,
              icon="assets/icon.ico" if sys.platform.startswith("win") else None)
