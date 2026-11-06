// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// A saved group of covers as one small card of the Case step: the name the person gave it, and under it, smaller, its case and its games.
// One choice out of several (a radio button): the chosen card has the sky-blue edge, the others the quiet edge of a control.
import QtQuick
import "."

Rectangle {
    id: card
    property string title: ""
    property string subtitle: ""
    property bool chosen: false
    signal picked()
    readonly property color edgeColor: chosen ? Theme.accent : Theme.edge

    implicitWidth: Theme.groupCardWidth
    implicitHeight: Math.max(Theme.touchMin, info.implicitHeight + 2 * Theme.s8)
    radius: Theme.radiusField
    color: "transparent"
    border.width: chosen ? Theme.focusRing : Theme.hairline
    border.color: edgeColor
    opacity: !enabled ? Theme.disabledOpacity : area.pressed ? Theme.pressedOpacity : 1
    activeFocusOnTab: true
    Accessible.role: Accessible.RadioButton
    Accessible.name: title + ". " + subtitle
    Accessible.checkable: true
    Accessible.checked: chosen
    Accessible.onPressAction: card.picked()

    Rectangle {                                       // keyboard focus ring
        anchors.fill: parent
        anchors.margins: -Theme.ringOffset
        radius: card.radius + Theme.ringOffset
        color: "transparent"
        border.width: card.activeFocus ? Theme.focusRing : 0
        border.color: Theme.text
    }
    Column {
        id: info
        x: Theme.s12
        y: (parent.height - height) / 2
        width: parent.width - 2 * Theme.s12
        Text {
            objectName: card.objectName + "_title"
            width: parent.width
            elide: Text.ElideRight
            maximumLineCount: 1
            text: card.title
            color: card.chosen ? Theme.accent : Theme.text
            font.pixelSize: Theme.bodySize
            font.bold: true
        }
        Text {
            objectName: card.objectName + "_subtitle"
            width: parent.width
            elide: Text.ElideRight
            maximumLineCount: 1
            text: card.subtitle
            color: Theme.muted
            font.pixelSize: Theme.smallSize
        }
    }
    MouseArea {
        id: area
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: card.picked()
    }
    Keys.onPressed: (event) => {
        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
            if (!event.isAutoRepeat) card.picked()
            event.accepted = true
        }
    }
}
