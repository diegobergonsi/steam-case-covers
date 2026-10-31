// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// A question that must be answered before anything changes (it covers the whole window). `ask(title, paragraphs, confirmText)` opens it;
// `paragraphs` is a list of {text, kind} with kind "main", "muted" or "warn". The safe button (Cancel) has the focus; Escape declines; Tab stays inside.
import QtQuick
import "."

FocusScope {
    id: dialog
    property string title: ""
    property var paragraphs: []
    property string confirmText: "OK"
    property string cancelText: "Cancel"
    property var returnTo: null                         // the item that had the focus before, so the keyboard comes back to it
    property Item focusBack: null                       // set by the screen: the button the keyboard goes back to (it may be greyed out while the question is open)
    signal confirmed()
    signal declined()
    signal alternated()
    property string prefix: "dlg"                       // the objectName prefix of the parts, so two dialogs in one window can be told apart
    property string alternateText: ""                  // a third choice between Cancel and the confirm; empty: none
    property bool single: false                          // an information box: only the confirm button ("OK")

    parent: Window.contentItem
    anchors.fill: parent
    z: 1
    visible: false
    Accessible.role: Accessible.Dialog
    Accessible.name: title

    function ask(heading, texts, yes, alt, info) {
        title = heading
        paragraphs = texts
        confirmText = yes ? yes : "OK"
        alternateText = alt ? alt : ""
        single = info === true
        returnTo = focusBack ? focusBack : Window.window ? Window.window.activeFocusItem : null
        visible = true
        var first = single ? confirm : cancel
        first.forceActiveFocus()
    }
    readonly property real maxCard: Math.min(Theme.dialogWidth, dialog.width - Theme.s32 - Theme.s32)       // the widest the card may be
    readonly property real pad: Theme.s24 + Theme.s24                                                        // its padding, left and right
    readonly property real maxText: maxCard - pad
    function wanted() {
        // the width of the longest line, measured on copies of the words laid out at the widest the card may be: the card then ends where the words end,
        // and the right side has no empty strip (the ends of wrapped lines are ragged, a card as wide as the widest possible line left one)
        var w = Math.min(titleProbe.contentWidth, maxText)
        for (var i = 0; i < probes.count; i++) w = Math.max(w, probes.itemAt(i).contentWidth)
        var row = confirm.implicitWidth
        var single = confirm.implicitWidth
        if (!dialog.single) { row += cancel.implicitWidth + Theme.s8; single = Math.max(single, cancel.implicitWidth) }
        if (alternate.visible) { row += alternate.implicitWidth + Theme.s8; single = Math.max(single, alternate.implicitWidth) }
        return Math.max(w, Math.min(row, maxText), Math.min(single, maxText))
    }
    function step(delta) {                              // the focus moves between the visible buttons and never leaves the dialog
        var list = []
        if (cancel.visible) list.push(cancel)
        if (alternate.visible) list.push(alternate)
        list.push(confirm)
        var at = 0
        for (var i = 0; i < list.length; i++) if (list[i].activeFocus) at = i
        list[(at + delta + list.length) % list.length].forceActiveFocus()
    }
    function close(answer, alt) {
        visible = false
        var back = returnTo
        if (alt === true) alternated(); else if (answer) confirmed(); else declined()
        Qt.callLater(function() { if (back && back.enabled && back.visible) back.forceActiveFocus() })       // after the screen has re-enabled its button
    }

    Keys.onPressed: (event) => {
        if (event.key === Qt.Key_Escape) {
            close(false)
            event.accepted = true
        } else if (event.key === Qt.Key_Tab || event.key === Qt.Key_Right) {
            step(1)
            event.accepted = true
        } else if (event.key === Qt.Key_Backtab || event.key === Qt.Key_Left) {
            step(-1)
            event.accepted = true
        }
    }

    Item {                                              // invisible copies of the words, only to measure them (see wanted)
        visible: false
        Text { id: titleProbe; width: dialog.maxText; text: dialog.title; wrapMode: Text.WordWrap; font.pixelSize: Theme.sectionSize; font.bold: true }
        Repeater {
            id: probes
            model: dialog.paragraphs
            delegate: Text { width: dialog.maxText; text: modelData.text; wrapMode: Text.WordWrap; font.pixelSize: Theme.bodySize }
        }
    }
    Rectangle {                                         // the dimmed window behind; it takes every click, so nothing behind can be reached
        anchors.fill: parent
        color: Theme.shadow
        opacity: Theme.scrimOpacity
    }
    MouseArea {
        anchors.fill: parent
        onWheel: (wheel) => wheel.accepted = true
    }
    Card {
        id: card
        objectName: dialog.prefix + "_card"
        width: Math.min(dialog.maxCard, Math.ceil(dialog.wanted()) + dialog.pad + Theme.hairline)         // as wide as its longest line, no wider
        height: content.implicitHeight + 2 * Theme.s24
        x: (dialog.width - width) / 2
        y: Math.max(Theme.s16, (dialog.height - height) / 2)
        Column {
            id: content
            x: Theme.s24
            y: Theme.s24
            width: card.width - 2 * Theme.s24
            spacing: Theme.s12
            Text {
                id: titleText
                objectName: dialog.prefix + "_title"
                width: parent.width
                text: dialog.title
                wrapMode: Text.WordWrap
                color: Theme.text
                font.pixelSize: Theme.sectionSize
                font.bold: true
            }
            Flickable {                                 // a lot of words scroll; the buttons stay in view
                id: body
                width: content.width
                height: Math.min(words.implicitHeight, Math.max(Theme.touchSize, dialog.height - Theme.s16 - Theme.s16 - Theme.s24 - Theme.s24 - titleText.height - buttons.height - Theme.s12 - Theme.s12 - Theme.s12 - Theme.s12))
                contentWidth: width
                contentHeight: words.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                Column {
                    id: words
                    width: body.width
                    spacing: Theme.s12
                    Repeater {
                        model: dialog.paragraphs
                        delegate: Text {
                            objectName: dialog.prefix + "_p" + index
                            width: words.width
                            text: modelData.text
                            wrapMode: Text.WordWrap
                            font.pixelSize: Theme.bodySize
                            color: modelData.kind === "warn" ? Theme.warning : modelData.kind === "muted" ? Theme.muted : Theme.text
                        }
                    }
                }
            }
            Item { width: Theme.hairline; height: Theme.s12 }       // the buttons stand apart from the last words (24 px in all)
            ButtonRow {
                id: buttons
                width: content.width
                QuietButton {
                    id: cancel
                    objectName: dialog.prefix + "_cancel"
                    visible: !dialog.single
                    text: dialog.cancelText
                    maxWidth: content.width
                    onClicked: dialog.close(false)
                }
                QuietButton {
                    id: alternate
                    objectName: dialog.prefix + "_alternate"
                    visible: dialog.alternateText !== "" && !dialog.single
                    text: dialog.alternateText
                    maxWidth: content.width
                    onClicked: dialog.close(false, true)
                }
                PrimaryButton {
                    id: confirm
                    objectName: dialog.prefix + "_confirm"
                    text: dialog.confirmText
                    maxWidth: content.width
                    onClicked: dialog.close(true)
                }
            }
        }
    }
}
