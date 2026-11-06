// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// The Games step of the manual flow: search by name, tick the games that get a console case.
import QtQuick
import QtQuick.Controls
import "."

ScreenFrame {
    id: screen
    readonly property var picker: shell.picker
    title: qsTr("Pick your games")
    subtitle: qsTr("Tick the games that get a case. Games you do not tick are left alone.")
    Component.onCompleted: picker.ensureLoaded()

    Section {
        objectName: "games_section_search"
        heading: qsTr("Find games")
        TextField {
            objectName: "games_search"
            width: parent.width
            height: Theme.touchMin
            placeholderText: qsTr("Search by name…")
            placeholderTextColor: Theme.faint
            color: Theme.text
            font.pixelSize: Theme.bodySize
            selectByMouse: true
            Accessible.name: qsTr("Search your games by name")
            background: Rectangle {
                radius: Theme.radiusField
                color: Theme.bg
                border.width: parent.activeFocus ? Theme.focusRing : Theme.hairline
                border.color: parent.activeFocus ? Theme.accent : Theme.edge
            }
            onTextChanged: screen.picker.query = text
        }
        Text {
            objectName: "games_count"
            width: parent.width
            text: qsTr("%n game selected|%n games selected", "", screen.picker.selectedCount)
            color: Theme.muted
            font.pixelSize: Theme.bodySize
        }
        ButtonRow {
            QuietButton { objectName: "games_all"; text: qsTr("Select all shown"); enabled: list.count > 0; onClicked: screen.picker.selectAllShown() }
            QuietButton { objectName: "games_clear"; text: qsTr("Clear"); enabled: screen.picker.selectedCount > 0; onClicked: screen.picker.clearAll() }
        }
    }
    Section {
        objectName: "games_section_list"
        heading: qsTr("Your games")
        StatusLine {
            objectName: "games_status"
            text: screen.picker.status
            kind: screen.picker.statusKind
            visible: text !== ""
        }
        ListView {
            id: list
            objectName: "games_list"
            width: parent.width
            height: Theme.listRows * Theme.touchMin
            clip: true
            model: screen.picker.model
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollCue { objectName: "games_scrollbar" }
            activeFocusOnTab: true                        // one stop for the whole list: the arrows move between games, Space ticks (a list only builds the rows it shows)
            keyNavigationEnabled: true
            highlightMoveDuration: Theme.dur(90)
            highlight: Rectangle {
                radius: Theme.radiusField
                color: "transparent"
                border.width: list.activeFocus ? Theme.focusRing : 0
                border.color: Theme.text
            }
            Accessible.role: Accessible.List
            Accessible.name: qsTr("Your games")
            onActiveFocusChanged: if (activeFocus && currentIndex < 0 && count > 0) currentIndex = 0       // a tab into the list lands on the first game
            Keys.onPressed: (event) => {
                if ((event.key === Qt.Key_Space || event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && list.currentItem) {
                    if (!event.isAutoRepeat) screen.picker.toggle(list.currentItem.rowAppid)
                    event.accepted = true
                }
            }
            delegate: Item {
                id: row
                objectName: "games_row_" + model.appid
                readonly property int rowAppid: model.appid
                width: list.width
                height: Theme.touchMin
                Accessible.role: Accessible.CheckBox
                Accessible.name: model.name
                Accessible.checkable: true
                Accessible.checked: model.selected
                Accessible.onToggleAction: screen.picker.toggle(model.appid)
                Accessible.onPressAction: screen.picker.toggle(model.appid)
                Rectangle {
                    anchors.fill: parent
                    radius: Theme.radiusField
                    color: hover.containsMouse ? Theme.raised : "transparent"
                }
                Rectangle {                                   // the tick box
                    id: box
                    x: Theme.s8
                    anchors.verticalCenter: parent.verticalCenter
                    width: Theme.iconSize
                    height: Theme.iconSize
                    radius: Theme.s4
                    color: model.selected ? Theme.accent : "transparent"
                    border.width: Theme.focusRing
                    border.color: model.selected ? Theme.accent : Theme.edge
                    Text {
                        anchors.centerIn: parent
                        visible: model.selected
                        text: "✓"
                        color: Theme.accentInk
                        font.pixelSize: Theme.bodySize
                        font.bold: true
                    }
                }
                Text {
                    x: box.x + box.width + Theme.s12
                    width: parent.width - x - Theme.s8
                    anchors.verticalCenter: parent.verticalCenter
                    text: model.name
                    color: Theme.text
                    font.pixelSize: Theme.bodySize
                    elide: Text.ElideRight
                }
                MouseArea {
                    id: hover
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: { list.currentIndex = index; list.forceActiveFocus(); screen.picker.toggle(model.appid) }
                }
            }
        }
    }

    footer: [
        PrimaryButton { objectName: "games_next"; text: qsTr("Next: Case →"); enabled: screen.picker.selectedCount > 0; onClicked: shell.next() }
    ]
}
