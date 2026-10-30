// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// The window: a left navigation and one screen at a time (docs/ui-guide.md). The screens here are placeholders; the real ones come in the next plans.
import QtQuick
import QtQuick.Controls
import "."

ApplicationWindow {
    id: win
    objectName: "window"
    width: 900
    height: 560
    minimumWidth: 640
    minimumHeight: 420
    visible: true
    title: "Steam Case Covers"
    color: Theme.bg

    readonly property int screenMs: Theme.dur(260)          // read by the tests
    readonly property var titles: ({
        "home": "Put every game in a physical case", "game_list": "Get your game list", "look": "Choose the look",
        "hundred": "Highlight your 100% games", "make": "Make your covers", "add": "Add them to Steam"
    })
    readonly property int navWidth: 210
    readonly property int rowHeight: 40
    readonly property int rowsTop: 72

    Binding { target: Theme; property: "reduce"; value: shell.reduceEffects }

    Rectangle {                                                   // the navigation
        id: nav
        objectName: "nav"
        width: win.navWidth
        height: parent.height
        color: Theme.navBg

        Rectangle {                                               // the highlight glides to the chosen step
            x: Theme.s8
            width: nav.width - 2 * Theme.s8
            height: win.rowHeight - 6
            radius: Theme.radiusField
            color: Theme.raised
            y: win.rowsTop + shell.current * win.rowHeight + 3
            Behavior on y { NumberAnimation { duration: Theme.dur(200); easing.type: Easing.OutCubic } }
        }
        Text {
            x: Theme.s24
            y: Theme.s24
            text: "Case Covers"
            color: Theme.text
            font.pixelSize: Theme.sectionSize
            font.bold: true
        }
        Column {
            y: win.rowsTop
            width: nav.width
            Repeater {
                model: shell.steps
                delegate: NavItem {
                    objectName: "nav_" + modelData.key
                    width: nav.width
                    label: modelData.label
                    stepState: modelData.state
                    selected: index === shell.current
                    onActivated: shell.go(index)
                }
            }
        }
        Row {                                                     // footer: Discord and updates
            x: Theme.s24
            y: nav.height - 84
            spacing: Theme.s8
            Image { visible: discordIcon !== ""; source: discordIcon; width: 20; height: 20; sourceSize.width: 40; sourceSize.height: 40; fillMode: Image.PreserveAspectFit }
            Text { objectName: "footer_discord"; text: "Discord"; color: Theme.muted; font.pixelSize: Theme.bodySize }
        }
        Text {
            objectName: "footer_updates"
            x: Theme.s24
            y: nav.height - 48
            text: "Check for updates"
            color: Theme.muted
            font.pixelSize: Theme.bodySize
        }
    }

    Item {                                                        // the screen: fades and slides in when the step changes
        id: screen
        x: win.navWidth + Theme.s32
        width: parent.width - win.navWidth - 2 * Theme.s32
        height: parent.height
        readonly property int index: shell.current
        readonly property string key: shell.steps[shell.current].key
        onIndexChanged: enter.restart()
        ParallelAnimation {
            id: enter
            NumberAnimation { target: screen; property: "opacity"; from: 0; to: 1; duration: Theme.dur(260) }
            NumberAnimation { target: screen; property: "x"; from: win.navWidth + Theme.s32 + 30; to: win.navWidth + Theme.s32; duration: Theme.dur(260); easing.type: Easing.OutCubic }
        }
        Text {
            id: heading
            y: Theme.s32
            width: parent.width
            text: win.titles[screen.key]
            color: Theme.text
            font.pixelSize: Theme.titleSize
            font.bold: true
            elide: Text.ElideRight
        }
        Card {
            y: heading.y + heading.height + Theme.s24
            width: parent.width
            height: 120
            Text {
                anchors.fill: parent
                anchors.margins: Theme.s16
                text: "This screen is built in the next plan."
                color: Theme.muted
                font.pixelSize: Theme.bodySize
                wrapMode: Text.WordWrap
            }
        }
        PrimaryButton {
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.bottomMargin: Theme.s32
            visible: shell.current < shell.steps.length - 1
            enabled: visible && shell.steps[shell.current + 1].state !== "locked"
            text: shell.current === 0 ? "Start →" : "Next →"
            onClicked: shell.next()
        }
    }
}
