// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// Stands in for a step whose real screen is built in a later plan.
import QtQuick
import "."

ScreenFrame {
    readonly property var titles: ({
        "home": "Put every game in a physical case", "game_list": "Get your game list", "look": "Choose the look",
        "hundred": "Highlight your 100% games", "make": "Make your covers", "add": "Add them to Steam"
    })
    title: titles[stepKey] || ""

    Section {
        heading: "Coming soon"
        Text {
            width: parent.width
            wrapMode: Text.WordWrap
            color: Theme.muted
            font.pixelSize: Theme.bodySize
            text: "This screen is built in a later plan."
        }
    }
    footer: [
        PrimaryButton {
            visible: shell.current < shell.steps.length - 1
            enabled: visible && shell.steps[shell.current + 1].state !== "locked"
            text: shell.current === 0 ? "Start →" : "Next →"
            onClicked: shell.next()
        }
    ]
}
