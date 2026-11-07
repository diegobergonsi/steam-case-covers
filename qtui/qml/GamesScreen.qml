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

    property string pendingCollection: ""               // the collection the question is about
    function pickCollection(id) {
        var plan = picker.collectionPlan(id)
        if (plan.games === 0) return
        if (!plan.ask) { picker.applyCollection(id, "add"); return }
        pendingCollection = id
        collectionDialog.ask(qsTr("You already ticked %n game|You already ticked %n games", "", plan.ticked), [
            {text: qsTr("\u201c%1\u201d has %n game on your list.|\u201c%1\u201d has %n games on your list.", "", plan.games).arg(plan.name), kind: "main"},
            {text: qsTr("Add keeps your ticks and ticks the collection too: %n game in total.|Add keeps your ticks and ticks the collection too: %n games in total.", "", plan.afterAdd), kind: "muted"},
            {text: qsTr("Replace unticks your games first: %n game in total.|Replace unticks your games first: %n games in total.", "", plan.games), kind: "muted"}],
            qsTr("Add them"), qsTr("Replace them"))
    }

    Section {
        objectName: "games_section_search"
        heading: qsTr("Find games")
        InputField {
            objectName: "games_search"
            width: parent.width
            placeholderText: qsTr("Search by name…")
            Accessible.name: qsTr("Search your games by name")
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
        Text {
            objectName: "games_collections_label"
            width: parent.width
            visible: screen.picker.collections.length > 0
            text: qsTr("Your collections")
            color: Theme.muted
            font.pixelSize: Theme.bodySize
        }
        CollectionPills {
            objectName: "games_collections"
            visible: screen.picker.collections.length > 0
            model: screen.picker.collections
            groupName: qsTr("Your collections")
            onPicked: (id) => screen.pickCollection(id)
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
            delegate: GameRow {
                objectName: "games_row_" + model.appid
                width: list.width
                appid: model.appid
                name: model.name
                selected: model.selected
                onToggled: { list.currentIndex = index; list.forceActiveFocus(); screen.picker.toggle(model.appid) }
            }
        }
    }

    ConfirmDialog {                                       // the safe button (Cancel) has the focus; the confirm adds, the one between them replaces
        id: collectionDialog
        objectName: "collections_dialog"
        prefix: "collections_dlg"
        onConfirmed: screen.picker.applyCollection(screen.pendingCollection, "add")
        onAlternated: screen.picker.applyCollection(screen.pendingCollection, "replace")
    }

    footer: [
        PrimaryButton { objectName: "games_next"; text: qsTr("Next: Case →"); enabled: screen.picker.selectedCount > 0; onClicked: shell.next() }
    ]
}
