# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""The Qt window.  Run:  python -m qtui        Check that it builds (no window is shown):  python -m qtui --selftest"""
import argparse
import os
import sys
import tempfile

from PySide6.QtGui import QGuiApplication

from qtui import steps
from qtui.app import create_engine, find_item
from qtui.shell import Shell


def selftest(shell, qml_dir):
    """Build the window and check that every navigation entry exists. Returns the exit code."""
    try:
        engine = create_engine(shell, qml_dir=qml_dir)
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 1
    missing = [k for k in steps.STEPS if find_item(engine.rootObjects()[0], "nav_" + k) is None]
    if missing:
        print("missing navigation entries: %s" % ", ".join(missing), file=sys.stderr)
        return 1
    print("selftest ok")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="qtui", description="Steam Case Covers, Qt window.")
    ap.add_argument("--selftest", action="store_true", help="build the window without showing it, check it, and exit")
    ap.add_argument("--qml-dir", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    app = QGuiApplication(sys.argv[:1])
    if args.selftest:
        with tempfile.TemporaryDirectory() as tmp:                      # never the user's real settings file
            return selftest(Shell(os.path.join(tmp, "settings.json")), args.qml_dir)
    shell = Shell()
    try:
        engine = create_engine(shell, qml_dir=args.qml_dir)
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 1
    code = app.exec()
    del engine
    return code


if __name__ == "__main__":
    sys.exit(main())
