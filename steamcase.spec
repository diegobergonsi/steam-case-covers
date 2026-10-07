# PyInstaller recipe. Build with:  pyinstaller steamcase.spec
import sys

a = Analysis(["gui.py"], datas=[("assets/frame.png", "assets")], excludes=["numpy", "matplotlib", "scipy", "pandas"])
pyz = PYZ(a.pure)

if sys.platform == "darwin":                       # macOS: folder-based .app (single-file .app is discouraged)
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="SteamCaseCovers", console=False)
    coll = COLLECT(exe, a.binaries, a.datas, name="SteamCaseCovers")
    app = BUNDLE(coll, name="SteamCaseCovers.app", bundle_identifier="com.github.diegobergonsi.steamcasecovers")
else:                                              # Windows and Linux: one file
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="SteamCaseCovers", console=False)
