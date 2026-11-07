// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// One game of a tick list: a tick box, the name and, at the right, a muted note (Manage names the other group the game is in). `toggled()` says the person
// asked to tick or untick it; the owner of the list does the ticking. At least 44 px tall.
import QtQuick
import "."

Item {
    id: row
    property int appid: 0
    property string name: ""
    property string tag: ""
    property bool selected: false
    readonly property int rowAppid: appid               // what a list's keyboard handler reads from its current row
    property bool standalone: false                     // a row outside a list (the checklist of a question) is a stop of its own for Tab; Space ticks it
    signal toggled()

    height: Theme.touchMin
    activeFocusOnTab: standalone && enabled
    Accessible.role: Accessible.CheckBox
    Accessible.name: tag === "" ? name : name + ". " + tag
    Accessible.checkable: true
    Accessible.checked: selected
    Accessible.onToggleAction: row.toggled()
    Accessible.onPressAction: row.toggled()
    Rectangle {
        anchors.fill: parent
        radius: Theme.radiusField
        color: hover.containsMouse ? Theme.raised : "transparent"
        border.width: row.activeFocus ? Theme.focusRing : 0                   // keyboard focus ring
        border.color: Theme.text
    }
    Rectangle {                                       // the tick box
        id: box
        x: Theme.s8
        anchors.verticalCenter: parent.verticalCenter
        width: Theme.iconSize
        height: Theme.iconSize
        radius: Theme.s4
        color: row.selected ? Theme.accent : "transparent"
        border.width: Theme.focusRing
        border.color: row.selected ? Theme.accent : Theme.edge
        Text {
            anchors.centerIn: parent
            visible: row.selected
            text: "✓"
            color: Theme.accentInk
            font.pixelSize: Theme.bodySize
            font.bold: true
        }
    }
    Text {
        id: tagText
        objectName: row.objectName + "_tag"
        anchors.right: parent.right
        anchors.rightMargin: Theme.s8
        anchors.verticalCenter: parent.verticalCenter
        width: Math.min(Math.ceil(implicitWidth), row.width / 2)
        visible: row.tag !== ""
        text: row.tag
        color: Theme.muted
        font.pixelSize: Theme.smallSize
        elide: Text.ElideRight
    }
    Text {
        x: box.x + box.width + Theme.s12
        width: parent.width - x - Theme.s8 - (tagText.visible ? tagText.width + Theme.s12 : 0)
        anchors.verticalCenter: parent.verticalCenter
        text: row.name
        color: Theme.text
        font.pixelSize: Theme.bodySize
        elide: Text.ElideRight
    }
    Keys.onPressed: (event) => {
        if (row.standalone && (event.key === Qt.Key_Space || event.key === Qt.Key_Return || event.key === Qt.Key_Enter)) {
            if (!event.isAutoRepeat) row.toggled()
            event.accepted = true
        }
    }
    MouseArea {
        id: hover
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: row.toggled()
    }
}
