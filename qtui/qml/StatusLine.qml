// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// What is happening, in words: muted while waiting, accent when good, the error colour when something is wrong.
import QtQuick
import "."

Text {
    property string kind: "wait"                       // wait | ok | warn | error
    width: parent ? parent.width : 0
    wrapMode: Text.WordWrap
    font.pixelSize: Theme.bodySize
    color: kind === "error" ? Theme.error : kind === "ok" ? Theme.accent : kind === "warn" ? Theme.warning : Theme.muted
    Accessible.role: Accessible.StaticText
    Accessible.name: text
}
