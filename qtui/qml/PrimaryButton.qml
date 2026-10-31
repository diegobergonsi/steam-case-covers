// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// The one filled button of a screen.
import QtQuick

Rectangle {
    id: root
    property string text: ""
    signal clicked()
    property bool quiet: false                     // the outlined look, for everything that is not the screen's main action
    readonly property bool filled: !quiet          // exactly one enabled filled button per screen (rule 2 of the guide)

    implicitWidth: Math.ceil(label.implicitWidth) + Theme.s32            // whole pixels: a button on a half pixel draws its text soft
    // never wider than the content area of a screen (what a section can hold): a longer text is cut with an ellipsis. System fonts differ a lot between computers.
    property real maxWidth: Math.max(Theme.controlHeight, Window.width - Theme.chromeWidth)
    width: Math.min(implicitWidth, maxWidth)
    implicitHeight: Theme.controlHeight
    radius: height / 2
    color: quiet ? (area.containsMouse ? Theme.raised : "transparent") : !enabled ? Theme.raised : area.containsMouse ? Qt.lighter(Theme.accent, Theme.hoverLift) : Theme.accent
    border.width: quiet ? Theme.hairline : 0
    border.color: Theme.edge
    opacity: quiet && !enabled ? Theme.disabledOpacity : 1
    scale: area.pressed ? 0.95 : 1
    activeFocusOnTab: enabled && visible
    Accessible.role: Accessible.Button
    Accessible.onPressAction: if (enabled) clicked()
    Accessible.name: text
    Behavior on scale { NumberAnimation { duration: Theme.dur(90) } }
    Behavior on color { ColorAnimation { duration: Theme.dur(120) } }

    Rectangle {                                   // keyboard focus ring
        anchors.fill: parent
        anchors.margins: -Theme.ringOffset
        radius: height / 2
        color: "transparent"
        border.width: root.activeFocus ? Theme.focusRing : 0
        border.color: Theme.text
    }
    Text {
        id: label
        x: Math.round((root.width - width) / 2)
        y: Math.round((root.height - height) / 2)
        width: Math.min(Math.ceil(implicitWidth), root.width - Theme.s32)
        elide: Text.ElideRight
        horizontalAlignment: Text.AlignHCenter
        text: root.text
        font.pixelSize: Theme.bodySize
        font.bold: true
        color: root.quiet ? Theme.text : root.enabled ? Theme.accentInk : Theme.faint
    }
    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        enabled: root.enabled
        cursorShape: Qt.PointingHandCursor
        onPressed: if (root.activeFocusOnTab) root.forceActiveFocus()       // a clicked button has the focus, so the keyboard can carry on from it
        onClicked: root.clicked()
    }
    Keys.onPressed: (event) => {                  // Return, numpad Enter and Space; a held key does not repeat the action
        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
            if (!event.isAutoRepeat && enabled) clicked()
            event.accepted = true
        }
    }
}
