# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""The sample cover QML shows on the Look screen, drawn by the engine and handed over as an image (image://preview/<hue>/<sat>/<val>/<theme>/<treatment>/<serial>)."""
import threading
from collections import OrderedDict

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider

import steamcase as sc

DEFAULT_SIZE = QSize(200, 300)
CACHE_SIZE = 16
MAX_SIDE = 2000                               # a request for a bigger picture than any screen shows is clamped


def _placeholder(size):
    img = QImage(size, QImage.Format_RGBA8888)
    img.fill(Qt.transparent)
    return img


def _parse(ident):
    """(hue, sat, val, theme or None, treatment or None) from a request id, or None when it is not one of ours."""
    parts = ident.split("/")
    if len(parts) != 6:
        return None
    try:
        hue, sat, val = int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None
    theme, treatment = parts[3], parts[4]
    if not (0 <= hue < 360 and 0 <= sat <= 100 and 0 <= val <= 100):
        return None
    if theme != "classic" and theme not in sc.THEMES:
        return None
    if treatment != "none" and treatment not in sc.TREATMENTS:
        return None
    return hue, sat, val, None if theme == "classic" else theme, None if treatment == "none" else treatment


class PreviewProvider(QQuickImageProvider):
    """Qt calls requestImage from its image threads: the engine call and the cache are behind one lock."""

    def __init__(self):
        super().__init__(QQuickImageProvider.ImageType.Image)
        self._lock = threading.Lock()
        self._cache = OrderedDict()           # (hue, sat, val, theme, treatment, w, h) -> QImage

    def requestImage(self, ident, size, requested):
        w, h = requested.width(), requested.height()
        want = DEFAULT_SIZE if w <= 0 or h <= 0 else QSize(min(w, MAX_SIDE), min(h, MAX_SIDE))
        request = _parse(ident)
        if request is None:
            return _placeholder(want)
        key = request + (want.width(), want.height())
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            try:
                hue, sat, val, theme, treatment = request
                pil = sc.preview_cover(hue, sat=sat, val=val, treatment=treatment, theme=theme).convert("RGBA")
                pil = pil.resize((want.width(), want.height()), sc.Image.LANCZOS)
                image = QImage(pil.tobytes(), pil.width, pil.height, pil.width * 4, QImage.Format_RGBA8888).copy()      # copy: the bytes object goes away
            except Exception:
                return QImage()                 # no picture at all: QML sees an error and keeps the old one (a blank picture would replace it)
            self._cache[key] = image
            while len(self._cache) > CACHE_SIZE:
                self._cache.popitem(last=False)
            return image
