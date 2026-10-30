# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Builds the QML window around a Shell. A QML error is an error here, not a warning on a blank window."""
import gc
import os
import sys

from PySide6.QtCore import QCoreApplication, QEvent, QUrl
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

import steamcase as sc
from qtui.preview import PreviewProvider
from qtui.system import SAVE_KEY

HERE = os.path.dirname(os.path.abspath(__file__))
_styled = False


def _asset_url(assets_dir, name):
    """The file as a URL for QML, or "" when it is missing (so a missing picture never becomes a QML warning)."""
    path = os.path.join(assets_dir, name)
    return QUrl.fromLocalFile(path).toString() if os.path.isfile(path) else ""


def create_engine(shell, qml_dir=None, assets_dir=None):
    """Load Main.qml with `shell` as context property `shell`. Raises RuntimeError with every QML message if the window cannot be built."""
    global _styled
    if not _styled:                                    # Qt allows this once, before the first QML is loaded
        QQuickStyle.setStyle("Basic")                  # never the desktop's own style (a KDE style once made the window fail to load)
        _styled = True
    qml_dir = qml_dir or os.path.join(HERE, "qml")
    assets_dir = assets_dir if assets_dir is not None else os.path.join(sc.HERE, "assets")
    icon = os.path.join(assets_dir, "icon.png")
    if os.path.isfile(icon):                           # the title bar and the task bar; a missing file just leaves the default
        QGuiApplication.setWindowIcon(QIcon(icon))
    engine = QQmlApplicationEngine()
    engine.addImageProvider("preview", PreviewProvider())        # the engine owns it
    problems = []
    engine.warnings.connect(lambda errors: problems.extend(e.toString() for e in errors))
    ctx = engine.rootContext()
    ctx.setContextProperty("shell", shell)
    ctx.setContextProperty("saveKey", SAVE_KEY)
    ctx.setContextProperty("familyHelp", sc.FAMILY_HELP)
    ctx.setContextProperty("discordIcon", _asset_url(assets_dir, "discord.png"))
    engine.load(QUrl.fromLocalFile(os.path.join(qml_dir, "Main.qml")))
    if problems or not engine.rootObjects():
        raise RuntimeError("The window could not be built:\n" + "\n".join(problems or ["Main.qml produced no window"]))
    return engine


def find_item(root, name):
    """The QML item with this objectName, searched in the visual tree (the delegates of a Repeater are not QObject children of the window), or None."""
    stack = [root.contentItem()]
    while stack:
        item = stack.pop()
        if item.objectName() == name:
            return item
        stack.extend(item.childItems())
    return None


MAX_LOG = 20000


def report_error(text, path=None):
    """Say why the window could not start. A packaged app has no console, so the message also goes to qtui-error.log next to the settings file
    (the first 20000 characters). Never raises: reporting an error must not become a second one."""
    try:
        if sys.stderr is not None:
            print(text, file=sys.stderr)
    except Exception:
        pass
    try:
        from qtui import settings
        path = path or os.path.join(os.path.dirname(settings.settings_path()), "qtui-error.log")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text[:MAX_LOG])
    except Exception:
        pass


def close_engine(engine):
    """Take the window down on purpose, while the shell it binds to is still alive. Left to Python's garbage collector, the shell can be freed
    first (the order differs between systems) and every binding then complains that `shell` is gone."""
    for root in engine.rootObjects():
        root.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)         # processEvents alone does not run deleteLater
    engine.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    gc.collect()                                                           # Qt objects with timers must die on the main thread, not in whichever thread the collector happens to run
