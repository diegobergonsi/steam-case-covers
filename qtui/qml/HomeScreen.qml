// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// Home: a Welcome the first time, a Dashboard after that, and the Undo section (Restore, Reset) always. Room for more "paths" later (Step by step is the first).
import QtQuick
import "."

ScreenFrame {
    id: screen
    objectName: "home_screen"
    readonly property var apply: shell.apply
    readonly property var stateText: ({"done": "Done", "active": "Next", "open": "Open", "locked": "Locked"})
    title: shell.returning ? "Welcome back" : "Cases for your games"
    subtitle: shell.returning ? "Pick up where you left off." : "Give every game in your Steam library a case, in about five minutes."

    Component.onCompleted: { apply.refresh(); apply.watching = true }
    Component.onDestruction: apply.watching = false

    Section {
        objectName: "home_section_main"
        heading: shell.returning ? "Your progress" : "Step by step"
        Text {
            visible: !shell.returning
            width: parent.width
            wrapMode: Text.WordWrap
            color: Theme.muted
            font.pixelSize: Theme.bodySize
            text: "Five short steps, nothing to install or run: get your game list, choose the look, optionally highlight your 100% games, make the covers, and add them to Steam."
        }
        Column {
            visible: shell.returning
            width: parent.width
            Repeater {
                model: shell.returning ? shell.steps.slice(1) : []
                delegate: Item {
                    id: row
                    objectName: "home_row_" + modelData.key
                    readonly property bool locked: modelData.state === "locked"
                    width: parent.width
                    height: Theme.touchSize
                    activeFocusOnTab: !locked
                    Accessible.role: Accessible.Button
                    Accessible.name: modelData.label + ", " + screen.stateText[modelData.state]
                    enabled: !locked                          // a disabled item is announced as unavailable
                    Accessible.onPressAction: if (!locked) shell.go(index + 1)
                    Rectangle {
                        anchors.fill: parent
                        radius: Theme.radiusField
                        color: "transparent"
                        border.width: row.activeFocus ? Theme.focusRing : 0
                        border.color: Theme.text
                    }
                    Text {
                        x: Theme.s8
                        width: parent.width - stateLabel.width - Theme.s24
                        anchors.verticalCenter: parent.verticalCenter
                        elide: Text.ElideRight
                        text: modelData.label + (modelData.hint !== "" ? " " + modelData.hint : "")
                        color: row.locked ? Theme.faint : Theme.text
                        font.pixelSize: Theme.bodySize
                    }
                    Text {
                        id: stateLabel
                        objectName: "home_state_" + modelData.key
                        x: parent.width - width - Theme.s8
                        anchors.verticalCenter: parent.verticalCenter
                        text: screen.stateText[modelData.state]
                        color: modelData.state === "done" ? Theme.done : modelData.state === "active" ? Theme.accent : Theme.faint
                        font.pixelSize: Theme.bodySize
                        font.bold: modelData.state !== "locked"
                    }
                    MouseArea { anchors.fill: parent; enabled: !row.locked; cursorShape: Qt.PointingHandCursor; onClicked: shell.go(index + 1) }
                    Keys.onPressed: (event) => {
                        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
                            if (!event.isAutoRepeat && !row.locked) shell.go(index + 1)
                            event.accepted = true
                        }
                    }
                }
            }
        }
    }
    Section {
        objectName: "home_section_undo"
        heading: "Undo"
        StatusLine {
            objectName: "home_note"
            text: screen.apply.note
            kind: screen.apply.noteKind === "warn" ? "warn" : "wait"
            font.bold: kind === "warn"
        }
        Text {
            objectName: "home_account"
            width: parent.width
            visible: text !== ""
            wrapMode: Text.WordWrap
            maximumLineCount: 2
            elide: Text.ElideRight
            color: Theme.text
            font.pixelSize: Theme.bodySize
            text: screen.apply.accountLabel
        }
        ChoiceChips {                                 // only with two or more Steam accounts; Restore and Reset change the account chosen here
            objectName: "home_accounts"
            groupName: "Steam account"
            width: parent.width
            visible: screen.apply.canChoose
            enabled: !screen.apply.busy && !shell.make.running
            model: screen.apply.accounts
            current: screen.apply.accountId !== "" ? screen.apply.accountId : screen.apply.accounts.length ? screen.apply.accounts[0].key : ""
            onChosen: (key) => screen.apply.chooseAccount(key)
        }
        ButtonRow {
            QuietButton { objectName: "home_restore"; text: "Restore previous artwork"; enabled: screen.apply.canRestore; onClicked: screen.apply.restore() }
            QuietButton { objectName: "home_reset"; text: "Reset to Steam's default art"; enabled: screen.apply.canReset; onClicked: screen.apply.reset() }
        }
        SwitchRow {
            objectName: "home_restart"
            enabled: screen.apply.canRestore || screen.apply.canReset
            label: "Start Steam again when finished"
            checked: screen.apply.restart
            onToggled: (value) => screen.apply.restart = value
        }
        StatusLine {
            objectName: "home_status"
            visible: text !== ""
            text: screen.apply.status
            kind: screen.apply.statusKind
        }
        FontMetrics { id: hintFont; font.pixelSize: Theme.smallSize }
        StatusLine {                                  // why Restore is greyed out; its line is always there, so nothing jumps when the probe answers
            objectName: "home_hint"
            height: Math.max(implicitHeight, hintFont.height)
            text: screen.apply.undoHint
            color: Theme.faint
            font.pixelSize: Theme.smallSize
        }
    }

    footer: [
        PrimaryButton {
            objectName: "home_main"
            text: shell.returning ? "Continue \u2192" : "Start \u2192"
            onClicked: shell.go(shell.returning ? shell.resume : 1)
        }
    ]
}
