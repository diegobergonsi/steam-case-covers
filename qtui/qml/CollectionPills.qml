// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// A row of buttons, one per Steam collection. `model` is a list of {id, label}; a click on one sends `picked(id)`. Two rows show; a link opens the rest.
// Pills below the two rows are not drawn and cannot be reached with Tab or a screen reader (`reachable`), so the keyboard never lands on a hidden one.
import QtQuick
import "."

Item {
    id: pills
    property var model: []
    property string groupName: ""                        // what the group is called for a screen reader
    property bool expanded: false
    signal picked(string id)
    readonly property real twoRows: 2 * Theme.touchMin + Theme.s8
    readonly property bool overflows: flow.implicitHeight > twoRows + 0.5
    Accessible.role: Accessible.Grouping
    Accessible.name: groupName
    implicitWidth: parent ? parent.width : 0
    width: implicitWidth
    implicitHeight: shown.height + (overflows ? Theme.s8 + more.height : 0)
    height: implicitHeight

    Item {
        id: shown
        width: pills.width
        height: pills.expanded || !pills.overflows ? flow.implicitHeight : pills.twoRows
        clip: true
        Flow {
            id: flow
            width: parent.width
            spacing: Theme.s8
            Repeater {
                model: pills.model
                delegate: Rectangle {
                    id: pill
                    objectName: pills.objectName + "_pill_" + modelData.id
                    readonly property string text: modelData.label
                    readonly property bool plain: label.textFormat === Text.PlainText
                    readonly property bool reachable: pills.expanded || y + height <= pills.twoRows + 0.5
                    width: Math.min(label.implicitWidth + 2 * Theme.s16, flow.width)
                    height: Theme.touchMin
                    radius: height / 2
                    color: area.containsMouse ? Qt.lighter(Theme.raised, Theme.hoverLift) : Theme.raised
                    border.width: Theme.hairline
                    border.color: Theme.edge
                    opacity: reachable ? 1 : 0
                    enabled: reachable
                    activeFocusOnTab: reachable
                    Accessible.ignored: !reachable
                    Accessible.role: Accessible.Button
                    Accessible.name: modelData.label
                    Accessible.onPressAction: pills.picked(modelData.id)
                    Behavior on color { ColorAnimation { duration: Theme.dur(120) } }

                    Rectangle {                                   // keyboard focus ring
                        anchors.fill: parent
                        anchors.margins: -Theme.ringOffset
                        radius: height / 2
                        color: "transparent"
                        border.width: pill.activeFocus ? Theme.focusRing : 0
                        border.color: Theme.text
                    }
                    Text {
                        id: label
                        objectName: pills.objectName + "_text_" + modelData.id
                        anchors.centerIn: parent
                        width: Math.min(implicitWidth, pill.width - 2 * Theme.s8)
                        elide: Text.ElideRight
                        horizontalAlignment: Text.AlignHCenter
                        textFormat: Text.PlainText                // a name is the player's own words, never markup
                        text: modelData.label
                        font.pixelSize: Theme.bodySize
                        font.bold: true
                        color: Theme.text
                    }
                    MouseArea {
                        id: area
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onPressed: pill.forceActiveFocus()
                        onClicked: pills.picked(modelData.id)
                    }
                    Keys.onPressed: (event) => {
                        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
                            if (!event.isAutoRepeat) pills.picked(modelData.id)
                            event.accepted = true
                        }
                    }
                }
            }
        }
    }
    QuietButton {
        id: more
        objectName: pills.objectName + "_more"
        y: shown.height + Theme.s8
        visible: pills.overflows
        text: pills.expanded ? qsTr("Show fewer") : qsTr("Show all %1 collections").arg(pills.model.length)
        onClicked: pills.expanded = !pills.expanded
    }
}
