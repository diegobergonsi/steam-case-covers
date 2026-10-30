# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""The Qt window.  Run:  python -m qtui        Check that it builds (no window is shown):  python -m qtui --selftest"""
import argparse
import gc
import os
import sys
import tempfile

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QGuiApplication

import steamcase as sc
from qtui import selfcheck, steps, system
from qtui.app import check_preview, close_engine, create_engine, find_item, report_error
from qtui.assets import missing_assets
from qtui.shell import Shell


def selftest(shell, qml_dir, assets_dir, log):
    """Build the window and check that the bundled pictures and every navigation entry exist. Returns the exit code."""
    gone = missing_assets(assets_dir)
    if gone:                                        # the window itself tolerates a missing picture, the build must not
        report_error("missing bundled files: %s" % ", ".join(gone), log)
        return 1
    problems = selfcheck.engine_problems()
    if problems:                                    # a bundle whose engine is broken must not print "selftest ok"
        report_error("the engine in this build does not work: %s" % "; ".join(problems), log)
        return 1
    try:
        engine = create_engine(shell, qml_dir=qml_dir, assets_dir=assets_dir)
    except RuntimeError as e:
        report_error(str(e), log)
        return 1
    root = engine.rootObjects()[0]
    missing = [k for k in steps.STEPS if find_item(root, "nav_" + k) is None]
    QCoreApplication.processEvents()
    if find_item(root, "home_main") is None:        # Home is the screen the window opens with
        missing.append("the Home screen")
    shell.go(1)                                     # step 1 imports parts (the file dialog) that only a packaged build can lack
    QCoreApplication.processEvents()
    if find_item(root, "gamelist_next") is None:
        missing.append("the Game list screen")
    shell.setFact("ready", True)                    # step 2 needs a ready game list
    shell.go(2)
    QCoreApplication.processEvents()
    if find_item(root, "look_next") is None:
        missing.append("the Look screen")
    shell.setFact("look_done", True)                # step 3 needs the look to be done
    shell.go(3)
    QCoreApplication.processEvents()
    if find_item(root, "hundred_next") is None:
        missing.append("the 100% games screen")
    shell.setFact("hundred_done", True)             # step 4 needs the 100% games step to be done
    shell.go(4)
    QCoreApplication.processEvents()
    if find_item(root, "make_main") is None:
        missing.append("the Make screen")
    shell.setFact("covers_made", True)              # step 5 needs covers
    shell.go(5)
    QCoreApplication.processEvents()
    if find_item(root, "add_main") is None:
        missing.append("the Add to Steam screen")
    if not check_preview(engine):
        missing.append("the preview picture")
    close_engine(engine)
    if missing:
        report_error("missing from the window: %s" % ", ".join(missing), log)
        return 1
    print("selftest ok")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="qtui", description="Steam Case Covers, Qt window.")
    ap.add_argument("--selftest", action="store_true", help="build the window without showing it, check it, and exit")
    ap.add_argument("--qml-dir", help=argparse.SUPPRESS)
    ap.add_argument("--assets-dir", help=argparse.SUPPRESS)
    ap.add_argument("--log", help=argparse.SUPPRESS)
    ap.add_argument("--version", action="store_true", help="print the version and exit")
    ap.add_argument("--check-network", action="store_true", help="for bug reports: does this computer reach Steam?")
    args = ap.parse_args(argv)
    if args.version:
        print("steam-case-covers %s" % sc.APP_VERSION)
        return 0
    if args.check_network:
        ok, msg = sc.check_network()
        print(("network ok: " if ok else "network FAILED: ") + msg)
        return 0 if ok else 1
    app = QGuiApplication(sys.argv[:1])
    assets_dir = args.assets_dir if args.assets_dir is not None else os.path.join(sc.HERE, "assets")
    if args.selftest:
        with tempfile.TemporaryDirectory() as tmp:                      # never the user's real settings file
            return selftest(Shell(os.path.join(tmp, "settings.json"), downloads=tmp, covers_dir=tmp), args.qml_dir, assets_dir, args.log)
    system.restore_child_env()
    shell = Shell()
    try:
        engine = create_engine(shell, qml_dir=args.qml_dir, assets_dir=assets_dir)
    except RuntimeError as e:
        report_error(str(e), args.log)
        return 1
    gc.collect()
    gc.freeze()                                         # the window's own objects live as long as the app: never collect them from an image thread
    code = app.exec()
    close_engine(engine)
    return code


if __name__ == "__main__":
    sys.exit(main())
