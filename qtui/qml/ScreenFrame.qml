// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// The frame every step's screen uses: a title, a one-line subtitle, sections that scroll when the window is short, and a footer whose
// buttons never scroll away (rule 9 of the guide). Put sections inside it, and the screen's buttons in `footer`.
import QtQuick
import QtQuick.Controls
import "."

Item {
    id: frame
    property string title: ""
    property string subtitle: ""
    property string stepKey: ""                       // set by the window
    property bool frozen: false                       // the controls are greyed and inert (the page still scrolls): the choices must not change while covers are made
    default property alias content: body.data
    property alias footer: footerRow.data
    readonly property real footerTop: footerRow.y     // where the footer buttons start: a message may sit above it

    Text {
        id: heading
        objectName: "screen_title"
        y: Theme.s32
        width: parent.width
        text: frame.title
        color: Theme.text
        font.pixelSize: Theme.titleSize
        font.bold: true
        elide: Text.ElideRight
    }
    Text {
        id: sub
        y: heading.y + heading.height + Theme.s4
        width: parent.width
        text: frame.subtitle
        color: Theme.muted
        font.pixelSize: Theme.bodySize
        wrapMode: Text.WordWrap
    }
    Flickable {
        id: scroller
        objectName: "screen_scroller"
        y: sub.y + sub.height + Theme.s16
        width: parent.width
        height: Math.max(0, footerRow.y - y - Theme.s16)
        contentWidth: width
        contentHeight: body.implicitHeight + Theme.s16       // room for the shadow of the last section
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollCue { id: bar; objectName: "screen_scrollbar" }   // the fade below reads its `size` too
        Column {
            id: body
            enabled: !frame.frozen
            opacity: enabled ? 1 : Theme.disabledOpacity
            width: scroller.width - Theme.s8              // the shadows of the sections need a little room on the right
            spacing: Theme.s24                            // sections sit 24 px apart (rule 7 of the guide)
        }
    }
    Rectangle {                                           // the bottom edge melts away while there is more below: the page looks cut off on purpose
        objectName: "screen_fade"
        visible: bar.size < 1 && !scroller.atYEnd
        y: scroller.y + scroller.height - height
        width: scroller.width
        height: Theme.s48
        gradient: Gradient {
            GradientStop { position: 0; color: Qt.alpha(Theme.bg, 0) }
            GradientStop { position: 1; color: Theme.bg }
        }
    }
    Row {
        id: footerRow
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Theme.s32
        enabled: !frame.frozen
        spacing: Theme.s8
    }
}
