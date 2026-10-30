// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// What was chosen in the earlier steps, as chips: "Colour  Teal". Each chip leads back to the step that changes it (`chosen(step)`, an index of the steps).
// `model` is a list of {key, label, value, step}. The whole group counts as one control.
import QtQuick
import "."

Flow {
    id: summary
    property var model: []
    signal chosen(int step)
    spacing: Theme.s8
    Accessible.role: Accessible.Grouping
    Accessible.name: "Your choices"

    Repeater {
        model: summary.model
        delegate: Rectangle {
            id: chip
            objectName: summary.objectName + "_chip_" + modelData.key
            width: Math.min(names.implicitWidth + Theme.s8 + values.implicitWidth + 2 * Theme.s16, summary.width)
            height: Theme.touchSize
            radius: height / 2
            color: area.containsMouse ? Qt.lighter(Theme.raised, Theme.hoverLift) : Theme.raised
            Behavior on color { ColorAnimation { duration: Theme.dur(120) } }
            activeFocusOnTab: true
            Accessible.role: Accessible.Button
            Accessible.name: modelData.label + ": " + modelData.value + ". Change"
            Accessible.onPressAction: summary.chosen(modelData.step)
            Rectangle {                                   // keyboard focus ring
                anchors.fill: parent
                anchors.margins: -Theme.ringOffset
                radius: height / 2
                color: "transparent"
                border.width: chip.activeFocus ? Theme.focusRing : 0
                border.color: Theme.text
            }
            Text {
                id: names
                x: Theme.s16
                anchors.verticalCenter: parent.verticalCenter
                text: modelData.label
                color: Theme.muted
                font.pixelSize: Theme.bodySize
            }
            Text {
                id: values
                x: names.x + names.width + Theme.s8
                width: Math.max(0, chip.width - x - Theme.s16)
                anchors.verticalCenter: parent.verticalCenter
                text: modelData.value
                elide: Text.ElideRight
                color: Theme.text
                font.pixelSize: Theme.bodySize
                font.bold: true
            }
            MouseArea {
                id: area
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: summary.chosen(modelData.step)
            }
            Keys.onPressed: (event) => {
                if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
                    if (!event.isAutoRepeat) summary.chosen(modelData.step)
                    event.accepted = true
                }
            }
        }
    }
}
