// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// Home: a Welcome the first time, a Dashboard after that. Two cards (the ways to make covers), the progress of the way in use, and the Undo section (Restore, Reset) always.
import QtQuick
import "."

ScreenFrame {
    id: screen
    objectName: "home_screen"
    readonly property var apply: shell.apply
    readonly property var stateText: ({"done": qsTr("Done"), "active": qsTr("Next"), "open": qsTr("Open"), "locked": qsTr("Locked")})
    title: shell.returning ? qsTr("Welcome back") : qsTr("Cases for your games")
    subtitle: shell.returning ? qsTr("Pick up where you left off.") : qsTr("Give every game in your Steam library a case, in about five minutes.")

    Component.onCompleted: { apply.refresh(); apply.watching = true; apply.groupTicks.refresh() }
    Component.onDestruction: apply.watching = false

    function blocked(flow) { return flow !== shell.flow && !shell.canSwitch }          // the other way, while covers are made or added
    function cue(flow) {                              // what a click on the card of a way does
        if (blocked(flow)) return qsTr("Wait until this finishes")
        return shell.returning && flow === shell.flow ? qsTr("Continue \u2192") : qsTr("Start \u2192")
    }

    Section {
        objectName: "home_section_paths"
        heading: qsTr("Choose your way")
        Grid {
            id: paths
            width: parent.width
            columns: width >= 2 * Theme.pathCardMinWidth + Theme.s16 ? 2 : 1
            spacing: Theme.s16
            readonly property real cardWidth: columns === 2 ? (width - spacing) / 2 : width
            readonly property real cardHeight: Math.max(natural.implicitHeight, manual.implicitHeight)
            PathCard {
                id: natural
                objectName: "home_card_natural"
                width: paths.cardWidth
                height: paths.columns === 2 ? paths.cardHeight : implicitHeight          // side by side, the two are as tall as the taller
                lead: true
                tag: qsTr("Best for most people")
                title: qsTr("The same case for every game on your list")
                line: qsTr("Choose a look once. Every game on your list gets it.")
                steps: qsTr("%n step|%n steps", "", shell.stepCount("natural"))
                cue: screen.cue("natural")
                blocked: screen.blocked("natural")
                onActivated: shell.startPath("natural")
            }
            PathCard {
                id: manual
                objectName: "home_card_manual"
                width: paths.cardWidth
                height: paths.columns === 2 ? paths.cardHeight : implicitHeight
                title: qsTr("Pick games, choose their cases")
                line: qsTr("Put games in groups and give each group its own case.")
                steps: qsTr("%n step|%n steps", "", shell.stepCount("manual"))
                cue: screen.cue("manual")
                blocked: screen.blocked("manual")
                onActivated: shell.startPath("manual")
            }
        }
    }
    Section {
        objectName: "home_section_progress"
        visible: shell.returning
        heading: qsTr("Your progress: %1").arg(shell.flowName)
        Column {
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
        // only when there is something to undo; with two or more accounts always, because the account is chosen in this card
        visible: screen.apply.canChoose || screen.apply.canRestore || screen.apply.canReset || screen.apply.busy || screen.apply.asking || shell.make.running
        heading: qsTr("Undo")
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
            groupName: qsTr("Steam account")
            width: parent.width
            visible: screen.apply.canChoose
            enabled: !screen.apply.busy && !shell.make.running
            model: screen.apply.accounts
            current: screen.apply.accountId !== "" ? screen.apply.accountId : screen.apply.accounts.length ? screen.apply.accounts[0].key : ""
            onChosen: (key) => screen.apply.chooseAccount(key)
        }
        ButtonRow {
            QuietButton { objectName: "home_restore"; text: qsTr("Restore previous artwork"); enabled: screen.apply.canRestore; onClicked: screen.apply.restore() }
            QuietButton { objectName: "home_reset"; text: qsTr("Reset to Steam's default art"); enabled: screen.apply.canReset; onClicked: screen.apply.reset() }
        }
        SwitchRow {
            objectName: "home_restart"
            enabled: screen.apply.canRestore || screen.apply.canReset
            label: qsTr("Start Steam again when finished")
            checked: screen.apply.restart
            onToggled: (value) => screen.apply.restart = value
        }
        StatusLine {
            objectName: "home_status"
            visible: text !== "" && screen.apply.statusKind !== "ok"          // progress and errors; what was done is said in a toast
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

    Section {
        objectName: "home_section_groups"
        heading: qsTr("Your groups")
        visible: screen.apply.groupTicks.choices.length > 0
        Text {
            width: parent.width
            wrapMode: Text.WordWrap
            color: Theme.muted
            font.pixelSize: Theme.bodySize
            text: qsTr("Reset leaves the covers of these groups on Steam. Tick a group to reset it too. That deletes the group.")
        }
        Repeater {
            model: screen.apply.groupTicks.choices
            delegate: SwitchRow {
                objectName: "home_group_" + modelData.id
                label: modelData.caption
                checked: modelData.ticked
                enabled: !screen.apply.busy
                onToggled: screen.apply.groupTicks.toggle(modelData.id)
            }
        }
    }
}
