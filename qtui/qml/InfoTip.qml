// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// The small "i": its text shows on hover or keyboard focus, and a click or Enter keeps it open (for touch screens). Escape closes it.
import QtQuick
import QtQuick.Controls
import "."

Item {
    id: tip
    property string text: ""
    property bool pinned: false
    readonly property bool shown: bubble.visible
    readonly property bool wanted: area.containsMouse || activeFocus || pinned
    width: Theme.infoSize
    height: Theme.infoSize
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: "More information"
    Accessible.description: text
    Accessible.onPressAction: pinned = !pinned

    // opened and closed by hand: a popup that the user closes (Escape, a click elsewhere) would otherwise lose a visible: binding for good
    function refresh() { if (wanted) bubble.open(); else bubble.close() }
    onWantedChanged: refresh()
    onPinnedChanged: refresh()                        // with keyboard focus the tip is 'wanted' all the time: pinning must still reopen it after Escape

    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: "transparent"
        border.width: tip.activeFocus ? Theme.focusRing : Theme.hairline
        border.color: tip.activeFocus ? Theme.text : Theme.accent
        Text { anchors.centerIn: parent; text: "i"; color: Theme.accent; font.pixelSize: Theme.smallSize; font.bold: true }
    }
    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: tip.pinned = !tip.pinned
    }
    Keys.onPressed: (event) => {
        if (event.key === Qt.Key_Escape) {
            tip.pinned = false
            bubble.close()
            event.accepted = true
        } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
            if (!event.isAutoRepeat) tip.pinned = !tip.pinned
            event.accepted = true
        }
    }
    onActiveFocusChanged: if (!activeFocus) pinned = false

    ToolTip {
        id: bubble
        delay: 0
        timeout: -1
        width: Math.min(Theme.tipMaxWidth, tip.Window.width - 2 * Theme.s32)
        padding: Theme.s12
        onClosed: tip.pinned = false
        contentItem: Text { text: tip.text; wrapMode: Text.WordWrap; color: Theme.text; font.pixelSize: Theme.tipTextSize }
        background: Rectangle { color: Theme.raised; radius: Theme.radiusField; border.width: Theme.hairline; border.color: Theme.edge }
    }
}
