// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// Step 5: add the covers to Steam. The wireframe "5 - Add to Steam": what will happen, the account, the switch, and the result.
import QtQuick
import "."

ScreenFrame {
    id: screen
    objectName: "add_screen"
    readonly property var apply: shell.apply
    readonly property var make: shell.make
    title: "Add them to Steam"
    subtitle: "Your covers are copied into your Steam account. A backup is made first."

    Component.onCompleted: { apply.refresh(); apply.watching = true }       // the screen asks whether Steam runs only while it is shown
    Component.onDestruction: apply.watching = false

    Section {
        objectName: "add_section_before"
        heading: "Before you apply"
        StatusLine {
            objectName: "add_note"
            text: screen.apply.note
            kind: screen.apply.noteKind === "warn" ? "warn" : "wait"
            font.bold: kind === "warn"
        }
        Text {
            objectName: "add_account"
            width: parent.width
            visible: text !== ""
            wrapMode: Text.WordWrap
            elide: Text.ElideRight
            maximumLineCount: 2
            color: Theme.text
            font.pixelSize: Theme.bodySize
            text: screen.apply.accountLabel
        }
        ChoiceChips {
            objectName: "add_accounts"
            groupName: "Steam account"
            width: parent.width
            visible: screen.apply.canChoose
            enabled: !screen.apply.busy && !screen.make.running
            model: screen.apply.accounts
            current: screen.apply.accountId !== "" ? screen.apply.accountId : screen.apply.accounts.length ? screen.apply.accounts[0].key : ""
            onChosen: (key) => screen.apply.chooseAccount(key)
        }
        SwitchRow {
            objectName: "add_restart"
            label: "Start Steam again when finished"
            checked: screen.apply.restart
            onToggled: (value) => screen.apply.restart = value
        }
    }
    Section {
        objectName: "add_section_result"
        heading: "Result"
        StatusLine {
            objectName: "add_status"
            text: screen.apply.status !== "" ? screen.apply.status : screen.apply.readyText
            kind: screen.apply.status !== "" ? screen.apply.statusKind : "wait"
        }
    }

    footer: [
        PrimaryButton {                               // one button for the whole step, so the keyboard focus stays: Apply, then the way home
            id: mainButton
            objectName: "add_main"
            text: screen.apply.busy ? "Applying\u2026" : screen.apply.applied ? "Go to Home \u2192" : "Apply to Steam"
            enabled: screen.apply.applied || screen.apply.canApply
            onClicked: screen.apply.applied ? shell.go(0) : screen.apply.apply()
        }
    ]

    ConfirmDialog {
        id: dialog
        objectName: "add_dialog"
        focusBack: mainButton
        onConfirmed: screen.apply.confirm()
        onDeclined: screen.apply.decline()
    }
    Connections {
        target: screen.apply
        function onConfirmNeeded(title, paragraphs, go, alt) { dialog.ask(title, paragraphs, go, alt) }
    }
}
