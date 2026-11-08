// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// The Case step of the manual flow: the real case of each console, one is picked for the games ticked in the Games step. Three sections beside a preview
// (above it on a narrow window): the cases, the group the games go in, the options. The one filled button is in the footer and says what it does now.
import QtQuick
import QtQuick.Controls
import "."

ScreenFrame {
    id: screen
    objectName: "case_screen"
    readonly property var cases: shell.cases
    readonly property var picker: shell.picker
    readonly property int ticked: picker.selectedCount
    title: qsTr("Pick a case")
    subtitle: qsTr("Pick the case for the games you ticked. You can do this again for other games, or go on.")

    PreviewLayout {
        previewName: "case_preview"
        source: screen.cases.previewSource

        Section {
            objectName: "case_section_grid"
            heading: qsTr("Choose a case")
            Flow {
                width: parent.width
                spacing: Theme.s12
                Repeater {
                    model: screen.cases.choices
                    delegate: Item {
                        id: cell
                        objectName: "case_" + modelData.key
                        readonly property bool chosen: screen.cases.selectedKey === modelData.key
                        width: Math.floor(parent.width / Theme.caseColumns) - Theme.s12
                        height: Theme.caseHeight + label.height + 3 * Theme.s8
                        activeFocusOnTab: true
                        Accessible.role: Accessible.RadioButton
                        Accessible.name: modelData.label
                        Accessible.checkable: true
                        Accessible.checked: chosen
                        Accessible.onPressAction: screen.cases.pick(modelData.key)
                        Rectangle {
                            anchors.fill: parent
                            radius: Theme.radiusField
                            color: hover.containsMouse ? Theme.raised : "transparent"
                            border.width: cell.chosen || cell.activeFocus ? Theme.focusRing : Theme.hairline
                            border.color: cell.chosen ? Theme.accent : cell.activeFocus ? Theme.text : Theme.edge
                        }
                        Image {
                            id: art
                            x: (parent.width - width) / 2
                            y: Theme.s8
                            width: Theme.caseWidth
                            height: Theme.caseHeight
                            sourceSize: Qt.size(2 * Theme.caseWidth, 2 * Theme.caseHeight)
                            source: modelData.source
                            smooth: true
                        }
                        Text {                                    // no case file picked yet: the card says what a click does
                            objectName: "case_custom_ask"
                            visible: modelData.ask
                            anchors.centerIn: art
                            width: art.width - 2 * Theme.s8
                            text: qsTr("Choose a file…")
                            color: Theme.muted
                            font.pixelSize: Theme.bodySize
                            wrapMode: Text.WordWrap
                            horizontalAlignment: Text.AlignHCenter
                        }
                        Text {
                            id: label
                            x: Theme.s8
                            y: art.y + art.height + Theme.s8
                            width: parent.width - 2 * Theme.s8
                            text: modelData.label
                            color: cell.chosen ? Theme.accent : Theme.text
                            font.pixelSize: Theme.bodySize
                            horizontalAlignment: Text.AlignHCenter
                            elide: Text.ElideRight
                        }
                        MouseArea {
                            id: hover
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: { cell.forceActiveFocus(); screen.cases.pick(modelData.key) }
                        }
                        Keys.onPressed: (event) => {
                            if (event.key === Qt.Key_Space || event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                                if (!event.isAutoRepeat) screen.cases.pick(modelData.key)
                                event.accepted = true
                            }
                        }
                    }
                }
            }
            Text {
                objectName: "case_own_hint"
                width: parent.width
                wrapMode: Text.WordWrap
                color: Theme.muted
                font.pixelSize: Theme.smallSize
                text: qsTr("My own case: a PNG of 600 x 900 pixels that is see-through where the art goes (at least 400 x 400). Picking a file replaces your last one.")
            }
            StatusLine {
                objectName: "case_own_error"
                visible: shell.owncase.error !== ""
                text: shell.owncase.error
                kind: "error"
            }
        }

        Section {
            objectName: "case_section_group"
            heading: screen.ticked > 0 ? qsTr("Add %n game to a group|Add %n games to a group", "", screen.ticked) : qsTr("Add games to a group")
            Flow {                                    // "New group" and the saved groups: one choice, like the case pictures
                width: parent.width
                spacing: Theme.s8
                GroupCard {
                    id: newCard
                    objectName: "case_card_new"
                    width: Math.min(Theme.groupCardWidth, parent.width)
                    title: qsTr("New group")
                    subtitle: screen.cases.selectedGroup === "" && screen.cases.selectedLabel !== "" ? screen.cases.selectedLabel : qsTr("Pick a case above")
                    chosen: screen.cases.selectedGroup === ""
                    onPicked: screen.cases.newGroup()
                }
                Repeater {
                    model: screen.cases.groupList
                    delegate: GroupCard {
                        objectName: "case_card_" + modelData.id
                        width: Math.min(Theme.groupCardWidth, parent.width)
                        title: modelData.name
                        subtitle: modelData.subtitle
                        chosen: screen.cases.selectedGroup === modelData.id
                        onPicked: screen.cases.pickGroup(modelData.id)
                    }
                }
                Text {                                // no saved group yet: the saved part of the row is greyed and says so
                    objectName: "case_no_groups"
                    visible: screen.cases.groupList.length === 0
                    height: Theme.touchMin
                    verticalAlignment: Text.AlignVCenter
                    width: Math.min(implicitWidth, parent.width)
                    wrapMode: Text.WordWrap
                    text: qsTr("You don't have any groups yet.")
                    color: Theme.faint
                    font.pixelSize: Theme.bodySize
                }
            }
            Flow {
                objectName: "case_colours"
                width: parent.width
                spacing: Theme.s8
                visible: screen.cases.selectedKey === "steam" && screen.cases.selectedGroup === ""
                Repeater {
                    id: colourRepeater
                    model: screen.cases.colourChoices.length
                    delegate: Swatch {
                        objectName: "case_colour_" + index
                        readonly property var info: screen.cases.colourChoices[index]
                        color: info.color
                        name: info.label
                        selected: screen.cases.colourIndex === index
                        tabStop: selected || (screen.cases.colourIndex < 0 && index === 0)
                        onPicked: screen.cases.pickColour(index)
                        onStep: (delta) => {
                            var to = Math.max(0, Math.min(screen.cases.colourChoices.length - 1, index + delta))
                            colourRepeater.itemAt(to).forceActiveFocus()
                            screen.cases.pickColour(to)
                        }
                    }
                }
            }
            InputField {                              // the name of a new group, which can be changed; a saved group shows its own, locked
                objectName: "case_group_name"
                visible: screen.cases.selectedKey !== ""
                readOnly: screen.cases.selectedGroup !== ""
                width: parent.width
                placeholderText: qsTr("Name this group")
                maximumLength: 40
                text: screen.cases.groupName
                Accessible.name: qsTr("Name of this group")
                onTextEdited: screen.cases.groupName = text
            }
            StatusLine {
                objectName: "case_error"
                visible: screen.cases.error !== ""
                text: screen.cases.error
            }
            Text {
                objectName: "case_so_far"
                visible: text !== ""
                width: parent.width
                wrapMode: Text.WordWrap
                color: Theme.muted
                font.pixelSize: Theme.bodySize
                text: screen.cases.soFar
            }
            ButtonRow {
                QuietButton { objectName: "case_more"; text: qsTr("Pick more games"); onClicked: shell.goKey("pick") }
                QuietButton {
                    id: deleteButton
                    objectName: "case_delete"
                    visible: screen.cases.selectedGroup !== ""
                    text: qsTr("Delete this group")
                    onClicked: deleteDialog.ask(qsTr("Delete the group \u201c%1\u201d?").arg(screen.cases.groupName),
                                                [{"text": qsTr("Its games lose this case here. Covers already on Steam stay until you Reset or make covers again."), "kind": "main"}],
                                                qsTr("Delete"))
                }
            }
        }
        Section {
            objectName: "case_section_options"
            heading: qsTr("Options")
            SwitchRow {
                objectName: "case_family"
                label: qsTr("Mark family games with a green corner")
                tip: familyHelp
                enabled: screen.cases.familyAvailable
                checked: screen.cases.family
                onToggled: (value) => screen.cases.family = value
            }
            StatusLine {
                objectName: "case_family_note"
                visible: !screen.cases.familyAvailable
                text: qsTr("Load your game list file in step 1 to use this (family games cannot be told apart without it).")
            }
            SwitchRow {
                objectName: "case_custom_art"
                label: qsTr("Use my own custom art where I have it")
                tip: customArtHelp
                checked: shell.look.useCustomArt
                onToggled: (value) => shell.look.useCustomArt = value
            }
        }
    }
    ConfirmDialog {                                       // deleting a group asks first; the safe button (Cancel) has the focus
        id: deleteDialog
        objectName: "case_delete_dialog"
        prefix: "case_delete_dlg"
        focusBack: deleteButton
        onConfirmed: {
            screen.cases.deleteGroup(screen.cases.selectedGroup)
            Qt.callLater(function() { newCard.forceActiveFocus() })              // the delete button is gone: the keyboard goes to the card that is chosen now
        }
    }

    footer: [
        PrimaryButton {
            objectName: "case_main"
            text: !screen.cases.canAssign ? qsTr("Next \u2192")
                  : screen.cases.selectedGroup !== "" ? qsTr("Add %n game to %1|Add %n games to %1", "", screen.ticked).arg(screen.cases.groupName)
                  : qsTr("Use this case for %n game|Use this case for %n games", "", screen.ticked)
            enabled: screen.cases.canAssign || screen.cases.assignedCount > 0
            onClicked: screen.cases.canAssign ? screen.cases.assign() : shell.next()
        }
    ]
}
