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
    title: qsTr("Make your covers")
    subtitle: qsTr("Downloads each game's artwork from Steam and builds the covers on your computer.")

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
            source: shell.flow === "manual" && shell.cases.previewKey !== "" ? "image://preview/platform/" + shell.cases.previewKey + "/1" : screen.look.previewSource
        }
        Column {
            id: sections
            x: layout.narrow ? 0 : preview.width + Theme.s24
            y: layout.narrow ? Theme.previewHeight + Theme.s24 : 0
            width: layout.width - x
            spacing: Theme.s24

            Section {
                objectName: "make_section_choices"
                heading: qsTr("Your choices")
                ChoiceSummary {
                    objectName: "make_choices"
                    width: parent.width
                    model: screen.make.choices
                    onChosen: (step) => shell.go(step)
                }
            }
            Section {
                objectName: "make_section_groups"
                heading: qsTr("Your groups")
                visible: shell.flow === "natural" && screen.make.groupTicks.choices.length > 0
                Text {
                    width: parent.width
                    wrapMode: Text.WordWrap
                    color: Theme.muted
                    font.pixelSize: Theme.bodySize
                    text: qsTr("These groups of covers were made by hand, so they are left as they are. Tick a group to repaint its covers with the look above. That deletes the group.")
                }
                Repeater {
                    model: screen.make.groupTicks.choices
                    delegate: SwitchRow {
                        objectName: "make_group_" + modelData.id
                        label: modelData.caption
                        checked: modelData.ticked
                        enabled: screen.make.canMake
                        onToggled: screen.make.groupTicks.toggle(modelData.id)
                    }
                }
            }
            Section {
                objectName: "make_section_progress"
                heading: qsTr("Progress")
                ProgressBar { objectName: "make_progress"; label: qsTr("Making the covers"); value: screen.make.progress }
                StatusLine { objectName: "make_status"; text: screen.make.status; kind: screen.make.statusKind }
                Flow {                                    // what was built: the first covers of the run
                    objectName: "make_thumbs"
                    width: parent.width
                    visible: screen.make.thumbs.length > 0
                    spacing: Theme.s8
                    Repeater {
                        model: screen.make.thumbs
                        delegate: Image {
                            objectName: "make_thumb_" + index
                            width: Theme.thumbWidth
                            height: Theme.thumbHeight
                            source: modelData
                            sourceSize.width: Theme.thumbPixels
                            fillMode: Image.PreserveAspectFit
                            asynchronous: true
                            cache: false                          // a cover made again under the same name must show the new picture
                            Accessible.role: Accessible.Graphic
                            Accessible.name: qsTr("Cover %1").arg(index + 1)
                        }
                    }
                }
                ButtonRow {
                    QuietButton { objectName: "make_folder"; text: qsTr("Open covers folder"); enabled: screen.make.done; onClicked: screen.make.openFolder() }
                }
            }
        }
    }

    footer: [
        QuietButton {                                 // after a run: make them again (the same question is asked if covers would be replaced)
            objectName: "make_again"
            text: qsTr("Make again")
            visible: screen.make.done && !screen.make.running
            enabled: screen.make.canMake
            onClicked: screen.make.start()
        },
        PrimaryButton {                               // one button for the whole job, so the keyboard focus stays: Make covers, Cancel, Next
            id: mainButton
            objectName: "make_main"
            text: screen.make.running ? qsTr("Cancel") : screen.make.done ? screen.make.nextText : qsTr("Make covers")
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
                                        {"text": qsTr("Steam keeps showing your current art until you add the new covers in step 5."), "kind": "muted"}], qsTr("Replace them"))
    }
    Component.onCompleted: {
        make.groupTicks.refresh()                       // the manual way may have changed them since this screen was last shown
        if (make.asking && make.questionTitle !== "") openQuestion()       // the question came while another screen was shown
    }
    Connections {
        target: screen.make
        function onConfirmNeeded(title, sentence) { screen.openQuestion() }
    }
}
