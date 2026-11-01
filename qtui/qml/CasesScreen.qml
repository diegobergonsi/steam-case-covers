// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// The Case step of the manual flow: the real case of each console, one is picked for the games ticked in the Games step.
import QtQuick
import QtQuick.Controls
import "."

ScreenFrame {
    id: screen
    readonly property var cases: shell.cases
    readonly property var picker: shell.picker
    title: "Pick a case"
    subtitle: "Pick the case for the games you ticked. You can do this again for other games, or go on."

    Section {
        objectName: "case_section_grid"
        heading: "Cases"
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
                        source: "image://preview/platform/" + modelData.key + "/1"
                        smooth: true
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
    }
    Section {
        objectName: "case_section_groups"
        heading: "Your groups"
        visible: screen.cases.groupList.length > 0
        Text {
            objectName: "case_group_intro"
            width: parent.width
            wrapMode: Text.WordWrap
            color: Theme.muted
            font.pixelSize: Theme.bodySize
            text: "The app remembers your groups. Pick one to add the games you ticked to it, or pick a case above for a new group."
        }
        Repeater {
            model: screen.cases.groupList
            delegate: ButtonRow {
                PrimaryButton {
                    objectName: "case_group_" + modelData.id
                    text: modelData.name + " · " + modelData.label + " · " + modelData.count + (modelData.count === 1 ? " game" : " games")
                    quiet: screen.cases.selectedGroup !== modelData.id
                    onClicked: screen.cases.pickGroup(modelData.id)
                }
                QuietButton {
                    objectName: "case_group_delete_" + modelData.id
                    text: "Delete group"
                    onClicked: screen.cases.deleteGroup(modelData.id)
                }
            }
        }
    }
    Section {
        objectName: "case_section_new_group"
        heading: "Name your group"
        visible: screen.cases.selectedKey !== "" && screen.cases.selectedGroup === ""
        Flow {
            objectName: "case_colours"
            width: parent.width
            spacing: Theme.s8
            visible: screen.cases.selectedKey === "steam"
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
        TextField {
            objectName: "case_group_name"
            width: parent.width
            height: Theme.controlHeight
            placeholderText: "Name this group"
            placeholderTextColor: Theme.faint
            color: Theme.text
            font.pixelSize: Theme.bodySize
            selectByMouse: true
            maximumLength: 40
            text: screen.cases.groupName
            Accessible.name: "Name of this group"
            background: Rectangle {
                radius: Theme.radiusField
                color: Theme.bg
                border.width: parent.activeFocus ? Theme.focusRing : Theme.hairline
                border.color: parent.activeFocus ? Theme.accent : Theme.edge
            }
            onTextEdited: screen.cases.groupName = text
        }
        StatusLine {
            objectName: "case_error"
            visible: screen.cases.error !== ""
            text: screen.cases.error
        }
    }
    Section {
        objectName: "case_section_games"
        heading: "Your games"
        Text {
            objectName: "case_applies"
            width: parent.width
            wrapMode: Text.WordWrap
            color: Theme.muted
            font.pixelSize: Theme.bodySize
            text: screen.picker.selectedCount > 0
                  ? "Applies to " + screen.picker.selectedCount + (screen.picker.selectedCount === 1 ? " ticked game." : " ticked games.")
                  : "No games are ticked now. Pick more games to give them a case, or go on."
        }
        ButtonRow {
            PrimaryButton {
                objectName: "case_assign"
                text: screen.cases.selectedGroup !== ""
                      ? "Add " + screen.picker.selectedCount + (screen.picker.selectedCount === 1 ? " game" : " games") + " to " + screen.cases.groupName
                      : "Use this case for " + screen.picker.selectedCount + (screen.picker.selectedCount === 1 ? " game" : " games")
                enabled: screen.cases.canAssign
                quiet: !enabled
                onClicked: screen.cases.assign()
            }
            QuietButton { objectName: "case_more"; text: "Pick more games"; onClicked: shell.goKey("pick") }
        }
        Repeater {
            model: screen.cases.summary
            delegate: Text {
                objectName: "case_summary_" + index
                width: parent.width
                color: Theme.text
                font.pixelSize: Theme.bodySize
                text: modelData.label + ": " + modelData.count + (modelData.count === 1 ? " game" : " games")
            }
        }
    }
    Section {
        objectName: "case_section_options"
        heading: "Options"
        SwitchRow {
            objectName: "case_family"
            label: "Mark family games with a green corner"
            tip: familyHelp
            enabled: screen.cases.familyAvailable
            checked: screen.cases.family
            onToggled: (value) => screen.cases.family = value
        }
        StatusLine {
            objectName: "case_family_note"
            visible: !screen.cases.familyAvailable
            text: "Load your game list file in step 1 to use this (family games cannot be told apart without it)."
        }
    }

    footer: [
        PrimaryButton { objectName: "case_next"; text: "Next →"; enabled: screen.cases.assignedCount > 0; onClicked: shell.next() }
    ]
}
