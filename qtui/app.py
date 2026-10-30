# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Builds the QML window around a Shell. A QML error is an error here, not a warning on a blank window."""
import os

from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

import steamcase as sc

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
    engine = QQmlApplicationEngine()
    problems = []
    engine.warnings.connect(lambda errors: problems.extend(e.toString() for e in errors))
    ctx = engine.rootContext()
    ctx.setContextProperty("shell", shell)
    ctx.setContextProperty("discordIcon", _asset_url(assets_dir, "discord.png"))
    ctx.setContextProperty("backdropArt", _asset_url(assets_dir, "default_art.png"))
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
