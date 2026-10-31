// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// A switch with its label and, optionally, an info tip. `checked` is set by the owner; `toggled(value)` says what the user asked for.
import QtQuick
import "."

Item {
    id: row
    property string label: ""
    property bool checked: false
    property string tip: ""
    signal toggled(bool value)

    width: parent ? parent.width : 0
    implicitHeight: Math.max(Theme.fieldRowHeight, caption.contentHeight + 2 * Theme.s4)
    height: implicitHeight
    activeFocusOnTab: enabled
    opacity: enabled ? 1 : Theme.disabledOpacity
    Accessible.role: Accessible.CheckBox
    Accessible.name: label
    Accessible.checked: checked
    Accessible.checkable: true
    Accessible.onToggleAction: row.toggled(!row.checked)
    Accessible.onPressAction: row.toggled(!row.checked)

    Rectangle {                                       // keyboard focus ring
        anchors.fill: parent
        radius: Theme.radiusField
        color: "transparent"
        border.width: row.activeFocus ? Theme.focusRing : 0
        border.color: Theme.text
    }
    Rectangle {
        id: track
        x: Theme.s4
        anchors.verticalCenter: parent.verticalCenter
        width: Theme.switchWidth
        height: Theme.switchHeight
        radius: height / 2
        color: row.checked ? Theme.accent : Theme.edge
        Behavior on color { ColorAnimation { duration: Theme.dur(200) } }
        Rectangle {
            id: knob
            y: Theme.knobInset
            width: Theme.knobSize
            height: Theme.knobSize
            radius: width / 2
            color: Theme.text
            x: row.checked ? track.width - width - Theme.knobInset : Theme.knobInset
            Behavior on x { NumberAnimation { duration: Theme.dur(200); easing.type: Easing.OutCubic } }
        }
    }
    Text {
        id: caption
        objectName: row.objectName + "_label"
        x: track.x + track.width + Theme.s12
        anchors.verticalCenter: parent.verticalCenter
        width: parent.width - x - (tipItem.visible ? tipItem.width + Theme.s12 : 0)
        text: row.label
        color: Theme.text
        font.pixelSize: Theme.bodySize
        wrapMode: Text.WordWrap                          // a long label wraps, it is never cut off
    }
    MouseArea {
        x: 0
        width: caption.x + caption.contentWidth
        height: parent.height
        cursorShape: Qt.PointingHandCursor
        onClicked: row.toggled(!row.checked)
    }
    InfoTip {
        id: tipItem
        objectName: row.objectName + "_tip"
        visible: row.tip !== ""
        text: row.tip
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
    }
    Keys.onPressed: (event) => {
        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
            if (!event.isAutoRepeat) row.toggled(!row.checked)
            event.accepted = true
        }
    }
}
