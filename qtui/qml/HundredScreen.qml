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
    title: "Highlight your 100% games"
    subtitle: "Optional. Games where you unlocked every achievement get a special mark."

    Item {
        id: layout
        width: parent.width
        readonly property bool narrow: width < Theme.previewWidth + Theme.s24 + Theme.sectionMinWidth
        readonly property real previewBlock: Theme.previewHeight + Theme.s8 + caption.height
        implicitHeight: narrow ? previewBlock + Theme.s24 + sections.implicitHeight : Math.max(previewBlock, sections.implicitHeight)
        height: implicitHeight

        PreviewCard {
            id: preview
            objectName: "hundred_preview"
            x: layout.narrow ? Math.max(0, (layout.width - width) / 2) : 0
            source: screen.look.previewSource
        }
        Text {                                            // the text, not the row, comes and goes: nothing moves under a finger
            id: caption
            objectName: "hundred_caption"
            x: preview.x
            y: preview.height + Theme.s8
            width: preview.width
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            color: Theme.muted
            font.pixelSize: Theme.bodySize
            text: screen.hundred.loaded && screen.look.treatment !== "none" ? "Preview of a 100% game" : ""
            Accessible.role: Accessible.StaticText
            Accessible.name: text
        }
        Column {
            id: sections
            x: layout.narrow ? 0 : preview.width + Theme.s24
            y: layout.narrow ? layout.previewBlock + Theme.s24 : 0
            width: layout.width - x
            spacing: Theme.s24

            Section {
                objectName: "hundred_section_page"
                heading: "Your games page"
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
                        text: "Open your games page and save it as games.html, choosing “Webpage, Complete”. The app notices the file by itself."
                    }
                    InfoTip { id: tip; objectName: "hundred_tip"; x: parent.width - width; text: pageHelp }
                }
                ButtonRow {
                    // the filled button is "Open my games page" until a page is loaded, then it turns quiet and "Next" takes over (same button: focus stays)
                    PrimaryButton { objectName: "hundred_open"; text: "Open my games page"; quiet: screen.hundred.loaded; onClicked: screen.hundred.openPage() }
                    QuietButton { objectName: "hundred_browse"; text: "Browse…"; onClicked: screen.hundred.browse() }
                    QuietButton { objectName: "hundred_copy"; text: "Copy link"; onClicked: screen.hundred.copyLink() }
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
                heading: "How to mark them"
                Text {
                    objectName: "hundred_locked_note"
                    width: parent.width
                    visible: !screen.hundred.styleEnabled
                    wrapMode: Text.WordWrap
                    color: Theme.faint
                    font.pixelSize: Theme.bodySize
                    text: "Load your games page first."
                }
                Column {
                    width: parent.width
                    spacing: Theme.s8
                    Text { text: "Marks"; color: Theme.muted; font.pixelSize: Theme.bodySize }
                    ChoiceChips {
                        objectName: "hundred_marks"
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
                    Text { text: "Case"; color: Theme.muted; font.pixelSize: Theme.bodySize }
                    ChoiceChips {
                        objectName: "hundred_style"
                        width: parent.width
                        enabled: screen.hundred.styleEnabled
                        model: screen.hundred.styles
                        current: screen.hundred.style
                        onChosen: (key) => screen.hundred.style = key
                    }
                }
            }
        }
    }

    footer: [
        PrimaryButton {
            objectName: "hundred_skip"
            text: "Skip this step →"
            quiet: true
            visible: !screen.hundred.loaded
            onClicked: { shell.setFact("hundred_done", true); shell.next() }
        },
        PrimaryButton {
            objectName: "hundred_next"
            text: "Next: Make →"
            visible: screen.hundred.loaded
            onClicked: { shell.setFact("hundred_done", true); shell.next() }
        }
    ]

    FileDialog {                                      // only when the desktop has no chooser of its own (see Hundred.browse)
        id: dialog
        objectName: "hundred_dialog"
        title: "Choose your saved games page"
        nameFilters: ["Web pages (*.html *.htm)", "All files (*)"]
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
