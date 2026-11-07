// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// A row of buttons, one per Steam collection. `model` is a list of {id, name, count, label} (label: the two together, for screen readers); a click on one sends `picked(id)`. Two rows show; a link opens the rest.
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
    readonly property real pad: Theme.ringOffset + Theme.focusRing          // room around the pills so a clip never cuts a focus ring
    readonly property real outset: -pad                                      // how far the clipping box reaches beyond the pills
    readonly property real bodyHeight: expanded || !overflows ? flow.implicitHeight : twoRows
    Accessible.role: Accessible.Grouping
    Accessible.name: groupName
    implicitWidth: parent ? parent.width : 0
    width: implicitWidth
    implicitHeight: bodyHeight + (overflows ? Theme.s8 + more.height : 0)
    height: implicitHeight

    Item {
        id: shown
        objectName: pills.objectName + "_shown"
        x: pills.outset
        y: pills.outset
        width: pills.width + 2 * pills.pad
        height: pills.bodyHeight + 2 * pills.pad
        clip: true
        Flow {
            id: flow
            x: pills.pad
            y: pills.pad
            width: pills.width
            spacing: Theme.s8
            Repeater {
                model: pills.model
                delegate: Rectangle {
                    id: pill
                    objectName: pills.objectName + "_pill_" + modelData.id
                    readonly property string text: modelData.label
                    readonly property bool plain: label.textFormat === Text.PlainText
                    readonly property bool reachable: pills.expanded || y + height <= pills.twoRows + 0.5
                    width: Math.min(label.implicitWidth + Theme.s4 + countText.implicitWidth + 2 * Theme.s16, flow.width)
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
                    Accessible.onPressAction: if (pill.reachable) pills.picked(modelData.id)
                    Behavior on color { ColorAnimation { duration: Theme.dur(120) } }

                    Rectangle {                                   // keyboard focus ring
                        anchors.fill: parent
                        anchors.margins: -Theme.ringOffset
                        radius: height / 2
                        color: "transparent"
                        border.width: pill.activeFocus ? Theme.focusRing : 0
                        border.color: Theme.text
                    }
                    Text {                                              // the name: cut with an ellipsis when too long, the count beside it never is
                        id: label
                        objectName: pills.objectName + "_text_" + modelData.id
                        x: Math.round((pill.width - width - Theme.s4 - countText.width) / 2)
                        y: Math.round((pill.height - height) / 2)
                        width: Math.min(implicitWidth, pill.width - 2 * Theme.s16 - Theme.s4 - countText.implicitWidth)
                        elide: Text.ElideRight
                        textFormat: Text.PlainText                // a name is the player's own words, never markup
                        text: modelData.name
                        font.pixelSize: Theme.bodySize
                        font.bold: true
                        color: Theme.text
                    }
                    Text {
                        id: countText
                        objectName: pills.objectName + "_count_" + modelData.id
                        x: label.x + label.width + Theme.s4
                        y: Math.round((pill.height - height) / 2)
                        text: "(" + modelData.count + ")"
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
