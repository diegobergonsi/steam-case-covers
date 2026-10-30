// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// How far a long job is: a track with a fill. `value` is 0 to 1. The numbers ("3 of 12") go in a StatusLine beside it, never only the bar.
import QtQuick
import "."

Item {
    id: bar
    property real value: 0
    property string label: "Progress"
    width: parent ? parent.width : 0
    implicitHeight: Theme.progressHeight
    height: implicitHeight
    Accessible.role: Accessible.ProgressBar
    Accessible.name: label

    Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: Theme.raised
        Rectangle {
            objectName: bar.objectName + "_fill"
            height: parent.height
            radius: height / 2
            color: Theme.accent
            width: parent.width * Math.max(0, Math.min(bar.value, 1))
            Behavior on width { NumberAnimation { duration: Theme.dur(120) } }
        }
    }
}
