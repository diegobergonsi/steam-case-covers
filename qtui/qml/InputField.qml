// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// A line of text the person types: the app's field look (8 px corners, the sky-blue ring while it has the focus), at least 44 px tall. The owner sets the width,
// the placeholder and the accessible name; a read-only field is drawn muted.
import QtQuick
import QtQuick.Controls
import "."

TextField {
    height: Theme.touchMin
    placeholderTextColor: Theme.faint
    color: readOnly ? Theme.muted : Theme.text
    font.pixelSize: Theme.bodySize
    selectByMouse: true
    background: Rectangle {
        radius: Theme.radiusField
        color: Theme.bg
        border.width: parent.activeFocus ? Theme.focusRing : Theme.hairline
        border.color: parent.activeFocus ? Theme.accent : Theme.edge
    }
}
