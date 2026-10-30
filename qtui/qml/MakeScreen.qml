// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// Step 4: make the covers. The wireframe "4 - Make": the preview beside the choices and the progress (above them when narrow).
import QtQuick
import "."

ScreenFrame {
    id: screen
    objectName: "make_screen"
    readonly property var make: shell.make
    readonly property var look: shell.look
    title: "Make your covers"
    subtitle: "Downloads each game's artwork from Steam and builds the covers on your computer."

    Item {
        id: layout
        width: parent.width
        readonly property bool narrow: width < Theme.previewWidth + Theme.s24 + Theme.sectionMinWidth
        implicitHeight: narrow ? Theme.previewHeight + Theme.s24 + sections.implicitHeight : Math.max(Theme.previewHeight, sections.implicitHeight)
        height: implicitHeight

        PreviewCard {
            id: preview
            objectName: "make_preview"
            x: layout.narrow ? Math.max(0, (layout.width - width) / 2) : 0
            source: screen.look.previewSource
        }
        Column {
            id: sections
            x: layout.narrow ? 0 : preview.width + Theme.s24
            y: layout.narrow ? Theme.previewHeight + Theme.s24 : 0
            width: layout.width - x
            spacing: Theme.s24

            Section {
                objectName: "make_section_choices"
                heading: "Your choices"
                ChoiceSummary {
                    objectName: "make_choices"
                    width: parent.width
                    model: screen.make.choices
                    onChosen: (step) => shell.go(step)
                }
            }
            Section {
                objectName: "make_section_progress"
                heading: "Progress"
                ProgressBar { objectName: "make_progress"; label: "Making the covers"; value: screen.make.progress }
                StatusLine { objectName: "make_status"; text: screen.make.status; kind: screen.make.statusKind }
                ButtonRow {
                    QuietButton { objectName: "make_folder"; text: "Open covers folder"; enabled: screen.make.done; onClicked: screen.make.openFolder() }
                }
            }
        }
    }

    footer: [
        QuietButton {                                 // after a run: make them again (the same question is asked if covers would be replaced)
            objectName: "make_again"
            text: "Make again"
            visible: screen.make.done && !screen.make.running
            enabled: screen.make.canMake
            onClicked: screen.make.start()
        },
        PrimaryButton {                               // one button for the whole job, so the keyboard focus stays: Make covers, Cancel, Next
            id: mainButton
            objectName: "make_main"
            text: screen.make.running ? "Cancel" : screen.make.done ? "Next: Add to Steam \u2192" : "Make covers"
            quiet: screen.make.running
            enabled: screen.make.running ? screen.make.canCancel : screen.make.done || screen.make.canMake
            onClicked: screen.make.running ? screen.make.cancel() : screen.make.done ? shell.next() : screen.make.start()
        }
    ]

    ConfirmDialog {
        id: dialog
        objectName: "make_dialog"
        focusBack: mainButton
        onConfirmed: screen.make.confirm()
        onDeclined: screen.make.decline()
    }
    function openQuestion() {
        dialog.ask(make.questionTitle, [{"text": make.questionText, "kind": "main"},
                                        {"text": "Steam keeps showing your current art until you add the new covers in step 5.", "kind": "muted"}], "Replace them")
    }
    Component.onCompleted: if (make.asking && make.questionTitle !== "") openQuestion()       // the question came while another screen was shown
    Connections {
        target: screen.make
        function onConfirmNeeded(title, sentence) { screen.openQuestion() }
    }
}
