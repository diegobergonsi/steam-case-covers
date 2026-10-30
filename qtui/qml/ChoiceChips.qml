// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// One choice out of a few, as pills. `model` is a list of {key, label}; `current` is the chosen key, kept by the owner (set it from `chosen`).
// Radio-button behaviour: only the chosen pill is a Tab stop, the arrow keys move the choice.
import QtQuick
import "."

Flow {
    id: chips
    property var model: []
    property string current: ""
    signal chosen(string key)
    spacing: Theme.s8

    function move(index, delta) {
        var n = chips.model.length
        var to = index + delta
        if (to >= 0 && to < n) {
            rep.itemAt(to).forceActiveFocus()                  // the focus moves first: the old chip stops being a Tab stop only after it has lost it
            chips.chosen(chips.model[to].key)
        }
    }

    Repeater {
        id: rep
        model: chips.model
        delegate: Rectangle {
            id: chip
            objectName: chips.objectName + "_chip_" + modelData.key
            readonly property bool selected: modelData.key === chips.current
            width: Math.min(label.implicitWidth + 2 * Theme.s16, chips.width)
            height: Theme.touchSize
            radius: height / 2
            color: selected ? Theme.accent : area.containsMouse ? Qt.lighter(Theme.raised, Theme.hoverLift) : Theme.raised
            Behavior on color { ColorAnimation { duration: Theme.dur(120) } }
            activeFocusOnTab: selected || (chips.current === "" && index === 0)
            Accessible.role: Accessible.RadioButton
            Accessible.name: modelData.label
            Accessible.checkable: true
            Accessible.checked: selected
            Accessible.onPressAction: chips.chosen(modelData.key)

            Rectangle {
                anchors.fill: parent
                anchors.margins: -Theme.ringOffset
                radius: height / 2
                color: "transparent"
                border.width: chip.activeFocus ? Theme.focusRing : 0
                border.color: Theme.text
            }
            Text {
                id: label
                anchors.centerIn: parent
                width: Math.min(implicitWidth, chip.width - 2 * Theme.s8)
                elide: Text.ElideRight
                horizontalAlignment: Text.AlignHCenter
                text: modelData.label
                font.pixelSize: Theme.bodySize
                font.bold: true
                color: chip.selected ? Theme.accentInk : Theme.text
            }
            MouseArea {
                id: area
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: chips.chosen(modelData.key)
            }
            Keys.onPressed: (event) => {
                var k = event.key
                if (k === Qt.Key_Right || k === Qt.Key_Down) chips.move(index, 1)
                else if (k === Qt.Key_Left || k === Qt.Key_Up) chips.move(index, -1)
                else if (k === Qt.Key_Home) chips.move(index, -index)
                else if (k === Qt.Key_End) chips.move(index, chips.model.length - 1 - index)
                else if (k === Qt.Key_Return || k === Qt.Key_Enter || k === Qt.Key_Space) { if (!event.isAutoRepeat) chips.chosen(modelData.key) }
                else return
                event.accepted = true
            }
        }
    }
}
