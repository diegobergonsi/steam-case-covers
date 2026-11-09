// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// The line of muted text under a sample cover. It is as tall as one line even when it has no text, so nothing moves when the text comes and goes.
import QtQuick
import "."

Text {
    FontMetrics { id: line; font.pixelSize: Theme.bodySize }
    height: line.height
    horizontalAlignment: Text.AlignHCenter
    wrapMode: Text.WordWrap
    color: Theme.muted
    font.pixelSize: Theme.bodySize
    Accessible.role: Accessible.StaticText
    Accessible.name: text
}
