// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// One of the ways to make covers, on Home: a title, a line, how many steps, and what happens on a click ("Start", "Continue"). The whole card is the button.
// The card that leads has a sky-blue edge and a tag; the other has the quiet edge of a control (visible against the section's card).
import QtQuick
import "."

Rectangle {
    id: card
    property string title: ""
    property string line: ""
    property string steps: ""
    property string cue: ""
    property string tag: ""
    property bool lead: false
    property bool blocked: false                      // the other way, while covers are made or added: the click does nothing
    signal activated()

    implicitHeight: info.implicitHeight + cueText.height + Theme.s8 + Theme.s32
    radius: Theme.radiusCard
    color: "transparent"
    border.width: lead ? Theme.focusRing : Theme.hairline
    border.color: lead ? Theme.accent : Theme.edge
    opacity: area.pressed ? Theme.pressedOpacity : 1
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: title + ". " + line + " " + steps + ". " + cue
    Accessible.onPressAction: card.activated()

    Rectangle {                                       // keyboard focus ring
        anchors.fill: parent
        anchors.margins: -Theme.ringOffset
        radius: card.radius + Theme.ringOffset
        color: "transparent"
        border.width: card.activeFocus ? Theme.focusRing : 0
        border.color: Theme.text
    }
    Column {
        id: info
        x: Theme.s16
        y: Theme.s16
        width: parent.width - 2 * Theme.s16
        spacing: Theme.s8
        Rectangle {
            visible: card.tag !== ""
            width: tagText.implicitWidth + 2 * Theme.s8
            height: tagText.implicitHeight + Theme.s4
            radius: height / 2
            color: Theme.raised
            Text {
                id: tagText
                objectName: card.objectName + "_tag"
                anchors.centerIn: parent
                text: card.tag
                color: Theme.accent
                font.pixelSize: Theme.smallSize
                font.bold: true
            }
        }
        Text {
            objectName: card.objectName + "_title"
            width: parent.width
            wrapMode: Text.WordWrap
            text: card.title
            color: Theme.text
            font.pixelSize: Theme.sectionSize
            font.bold: true
        }
        Text {
            objectName: card.objectName + "_line"
            width: parent.width
            wrapMode: Text.WordWrap
            text: card.line
            color: Theme.muted
            font.pixelSize: Theme.bodySize
        }
        Text {
            objectName: card.objectName + "_steps"
            width: parent.width
            text: card.steps
            color: Theme.muted
            font.pixelSize: Theme.bodySize
        }
    }
    Text {
        id: cueText
        objectName: card.objectName + "_cue"
        x: Theme.s16
        y: parent.height - height - Theme.s16
        width: parent.width - 2 * Theme.s16
        wrapMode: Text.WordWrap
        text: card.cue
        color: card.blocked ? Theme.muted : card.lead ? Theme.accent : Theme.text
        font.pixelSize: Theme.bodySize
        font.bold: !card.blocked
    }
    MouseArea {
        id: area
        anchors.fill: parent
        cursorShape: card.blocked ? Qt.ArrowCursor : Qt.PointingHandCursor
        onClicked: card.activated()
    }
    Keys.onPressed: (event) => {
        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
            if (!event.isAutoRepeat) card.activated()
            event.accepted = true
        }
    }
}
