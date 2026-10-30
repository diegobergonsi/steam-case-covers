// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// The window: a left navigation and one screen at a time (docs/ui-guide.md). The screens here are placeholders; the real ones come in the next plans.
import QtQuick
import QtQuick.Controls
import "."

ApplicationWindow {
    id: win
    objectName: "window"
    width: Theme.windowWidth
    height: Theme.windowHeight
    minimumWidth: Theme.windowMinWidth
    minimumHeight: Theme.windowMinHeight
    visible: true
    title: "Steam Case Covers"
    color: Theme.bg

    readonly property int screenMs: Theme.dur(260)          // read by the tests
    readonly property int navWidth: Theme.navWidth

    Binding { target: Theme; property: "reduce"; value: shell.reduceEffects }
    Timer { interval: 1500; repeat: true; running: true; onTriggered: shell.library.poll() }       // notices the saved game list

    Rectangle {                                                   // the navigation
        id: nav
        objectName: "nav"
        width: win.navWidth
        height: parent.height
        color: Theme.navBg

        Rectangle {                                               // the highlight glides to the chosen step
            x: Theme.s8
            width: nav.width - 2 * Theme.s8
            height: Theme.navHighlightHeight
            radius: Theme.radiusField
            color: Theme.raised
            y: Theme.navTop + shell.current * Theme.navRowHeight + Theme.navHighlightInset
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
            y: Theme.navTop
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
            Image { visible: discordIcon !== ""; source: discordIcon; width: Theme.iconSize; height: Theme.iconSize; sourceSize.width: Theme.iconPixels; sourceSize.height: Theme.iconPixels; fillMode: Image.PreserveAspectFit }
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
            NumberAnimation { target: screen; property: "x"; from: win.navWidth + Theme.s32 + Theme.slideOffset; to: win.navWidth + Theme.s32; duration: Theme.dur(260); easing.type: Easing.OutCubic }
        }
        Loader {
            anchors.fill: parent
            source: screen.key === "game_list" ? "GameListScreen.qml" : screen.key === "look" ? "LookScreen.qml" : "PlaceholderScreen.qml"
            onLoaded: item.stepKey = Qt.binding(function() { return screen.key })
        }
    }
}
