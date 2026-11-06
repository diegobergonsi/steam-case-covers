// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// A short message that shows for a moment and goes away by itself ("You picked a new case, so the saved group was unselected."). `show(text)` shows it;
// a second one replaces the first and starts the time again. Screen readers get it as an alert. The parent places it (x, y).
import QtQuick
import "."

Rectangle {
    id: toast
    property string message: ""
    property int showMs: Theme.toastMs
    readonly property bool active: timer.running
    function show(text) {
        message = text
        opacity = 1
        timer.restart()
    }

    width: label.width + 2 * Theme.s16
    height: label.height + 2 * Theme.s12
    radius: Theme.radiusField
    color: Theme.raised
    opacity: 0
    visible: opacity > 0
    Behavior on opacity { NumberAnimation { duration: Theme.dur(200) } }
    Accessible.role: Accessible.AlertMessage
    Accessible.name: message

    Text {
        id: label
        objectName: toast.objectName + "_text"
        x: Theme.s16
        y: Theme.s12
        width: Math.min(implicitWidth, Theme.tipMaxWidth - Theme.s32)
        wrapMode: Text.WordWrap
        text: toast.message
        color: Theme.text
        font.pixelSize: Theme.bodySize
    }
    Timer {
        id: timer
        interval: toast.showMs
        onTriggered: toast.opacity = 0
    }
}
