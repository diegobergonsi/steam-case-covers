// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// Step 3: the 100% games (optional). The wireframes "3 - 100% games" of the approved design: the preview beside two sections (above them when narrow).
import QtQuick
import QtQuick.Dialogs
import "."

ScreenFrame {
    id: screen
    objectName: "hundred_screen"
    readonly property var hundred: shell.hundred
    readonly property var look: shell.look
    title: qsTr("Highlight your 100% games")
    subtitle: qsTr("Optional. Games where you unlocked every achievement get a special mark.")

    PreviewLayout {
        previewName: "hundred_preview"
        source: screen.look.hundredSource
        underHeight: Theme.s8 + caption.height                  // the caption always keeps its line: nothing moves when it shows
        underPreview: [
            FontMetrics { id: captionFont; font.pixelSize: Theme.bodySize },        // also the height of the locked note below
            PreviewCaption {                                  // the text, not the row, comes and goes: nothing moves under a finger
                id: caption
                objectName: "hundred_caption"
                y: Theme.s8
                width: parent.width
                text: screen.hundred.loaded && screen.look.treatment !== "none" ? qsTr("Preview of a 100% game") : ""
            }
        ]

        Section {
            objectName: "hundred_section_page"
            heading: qsTr("Your games page")
            Item {
                width: parent.width
                implicitHeight: Math.max(intro.implicitHeight, tip.height)
                height: implicitHeight
                Text {
                    id: intro
                    objectName: "hundred_intro"
                    width: parent.width - tip.width - Theme.s8
                    wrapMode: Text.WordWrap
                    color: Theme.muted
                    font.pixelSize: Theme.bodySize
                    text: qsTr("Games where you unlocked every achievement can get a rosette and a ribbon (or the rosette alone, or no marks), and a gold case or border if you like. Steam shows them on your games page: open it, then save it as games.html, choosing “Webpage, Complete”. The app notices the file by itself.")
                }
                InfoTip { id: tip; objectName: "hundred_tip"; x: parent.width - width; text: pageHelp }
            }
            ButtonRow {
                // the filled button is "Open my games page" until a page is loaded, then it turns quiet and "Next" takes over (same button: focus stays)
                PrimaryButton { objectName: "hundred_open"; text: qsTr("Open my games page"); quiet: screen.hundred.loaded; onClicked: screen.hundred.openPage() }
                QuietButton { objectName: "hundred_browse"; text: qsTr("Browse…"); onClicked: screen.hundred.browse() }
                QuietButton { objectName: "hundred_copy"; text: qsTr("Copy link"); onClicked: screen.hundred.copyLink() }
            }
            StatusLine { objectName: "hundred_status"; text: screen.hundred.status; kind: screen.hundred.statusKind }
            StatusLine {
                objectName: "hundred_note"
                text: screen.hundred.note
                visible: text !== ""
                kind: "wait"
                color: Theme.faint
                font.pixelSize: Theme.smallSize
            }
        }
        Section {
            objectName: "hundred_section_mark"
            heading: qsTr("How to mark them")
            Text {
                objectName: "hundred_locked_note"
                width: parent.width
                height: captionFont.height                    // the line stays when the text goes: the chips below do not move
                wrapMode: Text.WordWrap
                color: Theme.faint
                font.pixelSize: Theme.bodySize
                text: screen.hundred.styleEnabled ? "" : qsTr("Load your games page first.")
            }
            Column {
                width: parent.width
                spacing: Theme.s8
                Text { text: qsTr("Marks"); color: Theme.muted; font.pixelSize: Theme.bodySize }
                ChoiceChips {
                    objectName: "hundred_marks"
                    groupName: qsTr("Marks")
                    width: parent.width
                    enabled: screen.hundred.marksEnabled
                    model: screen.hundred.markChoices
                    current: screen.hundred.marks
                    onChosen: (key) => screen.hundred.marks = key
                }
                Text {
                    objectName: "hundred_theme_note"
                    width: parent.width
                    visible: screen.hundred.themeNote !== ""
                    wrapMode: Text.WordWrap
                    color: Theme.faint
                    font.pixelSize: Theme.bodySize
                    text: screen.hundred.themeNote
                }
                Text { text: shell.flow === "manual" ? qsTr("Highlight") : qsTr("Case"); color: Theme.muted; font.pixelSize: Theme.bodySize }
                ChoiceChips {
                    objectName: "hundred_style"
                    groupName: shell.flow === "manual" ? qsTr("Highlight") : qsTr("Case")                  // what the screen reader says is what the screen says
                    width: parent.width
                    enabled: screen.hundred.styleEnabled
                    model: shell.flow === "manual" ? screen.hundred.manualStyles : screen.hundred.styles
                    current: shell.flow === "manual" && screen.hundred.style !== "none" ? "ribbon" : screen.hundred.style       // console cases have no gold: any case style means "highlight"
                    onChosen: (key) => screen.hundred.style = key
                }
            }
        }
    }

    footer: [
        PrimaryButton {                               // one button for both: "Skip" (quiet) without a page, "Next" (filled) with one, so the keyboard focus stays
            objectName: "hundred_next"
            text: screen.hundred.loaded ? qsTr("Next: Make \u2192") : qsTr("Skip this step \u2192")
            quiet: !screen.hundred.loaded
            enabled: !screen.hundred.busy             // a page is being read: Make must not go on with the one read before
            onClicked: { shell.setFact("hundred_done", true); shell.next() }
        }
    ]

    FileDialog {                                      // only when the desktop has no chooser of its own (see Hundred.browse)
        id: dialog
        objectName: "hundred_dialog"
        title: qsTr("Choose your saved games page")
        nameFilters: [qsTr("Web pages (*.html *.htm)"), qsTr("All files (*)")]
        onAccepted: screen.hundred.loadPageUrl(selectedFile.toString())
    }
    Connections {
        target: screen.hundred
        function onNeedDialog(folder) {
            dialog.currentFolder = screen.hundred.downloadsUrl
            dialog.open()
        }
    }
}
