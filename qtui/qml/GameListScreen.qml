// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// Step 1: get the game list. The wireframe "1 - Game list" of the approved design.
import QtQuick
import QtQuick.Dialogs
import Qt.labs.folderlistmodel           // not used here: Qt's own file dialog needs it, and the packaged self-test must notice if a build lacks it
import "."

ScreenFrame {
    id: screen
    readonly property var library: shell.library
    title: "Get your game list"
    subtitle: "Steam keeps it on a web page you save once."

    Section {
        objectName: "gamelist_section_list"
        heading: "Your game list"
        Text {
            width: parent.width
            wrapMode: Text.WordWrap
            color: Theme.muted
            font.pixelSize: Theme.bodySize
            text: "Steam keeps your game list on a web page. Open it and log in if asked. A page of text appears: press " + saveKey + " and save it, keeping the name userdata.json. The app notices the file by itself."
        }
        ButtonRow {
            // the one filled button of the screen is "Open the page" until a list is ready, then it turns quiet and "Next" takes over (same button: focus stays)
            PrimaryButton { objectName: "gamelist_open"; text: "Open the page in my browser"; quiet: screen.library.ready; onClicked: screen.library.openDownloadPage() }
            QuietButton { objectName: "gamelist_browse"; text: "Browse…"; onClicked: screen.library.browse() }
            QuietButton { objectName: "gamelist_copy"; text: "Copy link"; onClicked: screen.library.copyLink() }
        }
    }
    Section {
        objectName: "gamelist_section_skip"
        heading: "Or skip it"
        SwitchRow {
            objectName: "gamelist_installed"
            label: "Only my installed games (no file needed)"
            tip: familyHelp
            checked: screen.library.installedOnly
            onToggled: (value) => screen.library.installedOnly = value
        }
    }
    StatusLine {
        objectName: "gamelist_status"
        text: screen.library.status
        kind: screen.library.statusKind
    }

    footer: [
        PrimaryButton { objectName: "gamelist_next"; text: "Next →"; enabled: screen.library.ready; onClicked: shell.next() }
    ]

    FileDialog {                                      // only when the desktop has no chooser of its own (see Library.browse)
        id: dialog
        title: "Choose your userdata.json"
        nameFilters: ["JSON files (*.json)", "All files (*)"]
        onAccepted: screen.library.useFileUrl(selectedFile.toString())
    }
    Connections {
        target: screen.library
        function onNeedDialog(folder) {
            dialog.currentFolder = screen.library.downloadsUrl
            dialog.open()
        }
    }
}
