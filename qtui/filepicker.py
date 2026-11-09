# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""The desktop's own file chooser. On Linux the plain Qt dialog looks dated next to KDE's or GNOME's, so use theirs when it is installed."""
import os
import shutil
import subprocess
import sys
from qtui.i18n import tr


def pick_file(title, start_dir, kind=None):
    """The path the user chose; "" when they cancelled; None when no desktop chooser worked, so the caller shows the Qt dialog.
    `kind` is (description, patterns separated by spaces) of the files to show first."""
    if not sys.platform.startswith("linux"):
        return None
    start = (start_dir if start_dir and os.path.isdir(start_dir) else os.path.expanduser("~")).rstrip("/") + "/"
    what, patterns = kind or (tr("JSON files"), "*.json")          # looked up now, not when the module loads: the language is chosen after that
    everything = tr("All files")
    cmds = []
    if shutil.which("kdialog"):
        cmds.append(["kdialog", "--title", title, "--getopenfilename", start, "%s|%s (%s)\n*|%s" % (patterns, what, patterns, everything)])
    if shutil.which("zenity"):
        cmds.append(["zenity", "--file-selection", "--title=" + title, "--filename=" + start, "--file-filter=%s | %s" % (what, patterns), "--file-filter=%s | *" % everything])
    for cmd in cmds:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True)
        except OSError:
            continue
        if r.returncode == 0:
            return r.stdout.strip()
        if r.returncode == 1:                    # the user pressed Cancel
            return ""
    return None
