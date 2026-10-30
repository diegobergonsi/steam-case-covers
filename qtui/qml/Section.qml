// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// One section of a screen: a card with a heading. At most three controls inside (rule 4 of the guide).
import QtQuick
import "."

Card {
    id: section
    property string heading: ""
    property string note: ""                           // a short text at the right of the heading (the colour's name)
    default property alias content: inner.data
    width: parent ? parent.width : 0
    implicitHeight: headingText.height + inner.implicitHeight + 2 * Theme.s16 + Theme.s8
    height: implicitHeight

    Text {
        id: headingText
        x: Theme.s16
        y: Theme.s16
        width: parent.width - 2 * Theme.s16 - (noteText.text !== "" ? noteText.width + Theme.s12 : 0)
        text: section.heading
        color: Theme.text
        font.pixelSize: Theme.sectionSize
        font.bold: true
        elide: Text.ElideRight
    }
    Text {
        id: noteText
        objectName: section.objectName + "_note"
        x: parent.width - width - Theme.s16
        y: headingText.y + (headingText.height - height) / 2
        width: Math.min(implicitWidth, parent.width / 2)
        text: section.note
        color: Theme.muted
        font.pixelSize: Theme.bodySize
        elide: Text.ElideRight
        horizontalAlignment: Text.AlignRight
    }
    Column {
        id: inner
        x: Theme.s16
        y: Theme.s16 + headingText.height + Theme.s8
        width: parent.width - 2 * Theme.s16
        spacing: Theme.s12
    }
}
