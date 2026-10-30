// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// Step 2: the look. The wireframe "2 - Look" of the approved design: the preview beside three sections (it moves above them on a narrow window).
import QtQuick
import "."

ScreenFrame {
    id: screen
    readonly property var look: shell.look
    title: "Choose the look"
    subtitle: "The preview changes as you pick."

    // the track shows the case in its current colour; reading the three values here makes the binding follow them
    function stopsFor(which) { var tone = [look.hue, look.sat, look.val]; return look.trackColors(which) }

    Item {
        id: layout
        width: parent.width
        readonly property bool narrow: width < Theme.previewWidth + Theme.s24 + Theme.sectionMinWidth
        implicitHeight: narrow ? Theme.previewHeight + Theme.s24 + sections.implicitHeight : Math.max(Theme.previewHeight, sections.implicitHeight)
        height: implicitHeight

        PreviewCard {
            id: preview
            objectName: "look_preview"
            x: layout.narrow ? Math.max(0, (layout.width - width) / 2) : 0
            source: screen.look.previewSource
        }
        Column {
            id: sections
            x: layout.narrow ? 0 : preview.width + Theme.s24
            y: layout.narrow ? preview.height + Theme.s24 : 0
            width: layout.width - x
            spacing: Theme.s24

            Section {
                objectName: "look_section_colour"
                heading: "Case colour"
                Text { objectName: "look_tone_name"; width: parent.width; text: screen.look.toneName; color: Theme.muted; font.pixelSize: Theme.bodySize; elide: Text.ElideRight }
                Column {
                    width: parent.width
                    spacing: Theme.s4
                    Text { text: "Colour"; color: Theme.muted; font.pixelSize: Theme.smallSize }
                    GradientSlider { objectName: "look_hue"; width: parent.width; label: "Colour"; from: 0; to: 359; value: screen.look.hue
                        stops: screen.look.hueColors(); onMoved: (v) => screen.look.hue = v }
                    Text { text: "Colourfulness"; color: Theme.muted; font.pixelSize: Theme.smallSize }
                    GradientSlider { objectName: "look_sat"; width: parent.width; label: "Colourfulness"; from: 0; to: 100; value: screen.look.sat
                        stops: screen.stopsFor("sat"); onMoved: (v) => screen.look.sat = v }
                    Text { text: "Brightness"; color: Theme.muted; font.pixelSize: Theme.smallSize }
                    GradientSlider { objectName: "look_val"; width: parent.width; label: "Brightness"; from: 0; to: 100; value: screen.look.val
                        stops: screen.stopsFor("val"); onMoved: (v) => screen.look.val = v }
                }
                Flow {
                    width: parent.width
                    spacing: Theme.s4
                    Repeater {
                        model: screen.look.swatches.length          // a number, not the list: a new tone must not rebuild the swatches (the focused one would be destroyed)
                        delegate: Swatch {
                            objectName: "look_swatch_" + index
                            readonly property var info: screen.look.swatches[index]
                            color: info.color
                            name: info.name
                            selected: info.selected
                            onPicked: screen.look.pickSwatch(index)
                        }
                    }
                }
                StatusLine { objectName: "look_hint"; text: screen.look.toneHint; visible: text !== "" }
                StatusLine { objectName: "look_note"; text: screen.look.colourNote; visible: text !== ""; color: Theme.faint; font.pixelSize: Theme.smallSize }
            }
            Section {
                objectName: "look_section_theme"
                heading: "Theme"
                ChoiceChips {
                    objectName: "look_theme"
                    width: parent.width
                    model: [{"key": "classic", "label": "Classic"}, {"key": "halloween", "label": "Halloween"}]
                    current: screen.look.theme
                    onChosen: (key) => screen.look.theme = key
                }
            }
            Section {
                objectName: "look_section_art"
                heading: "Art"
                SwitchRow { objectName: "look_custom_art"; label: "Use my own custom art where I have it"; tip: customArtHelp
                    checked: screen.look.useCustomArt; onToggled: (v) => screen.look.useCustomArt = v }
                SwitchRow { objectName: "look_skip_blurry"; label: "Skip blurry covers"; tip: autoArtHelp
                    checked: screen.look.skipAutoArt; onToggled: (v) => screen.look.skipAutoArt = v }
            }
        }
    }

    footer: [
        PrimaryButton {
            objectName: "look_next"
            text: "Next: 100% games →"
            onClicked: { shell.setFact("look_done", true); shell.next() }
        }
    ]
}
