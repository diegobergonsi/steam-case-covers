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

    parent: Window.contentItem
    anchors.fill: parent
    z: 1
    visible: false
    Accessible.role: Accessible.Dialog
    Accessible.name: title

    function ask(heading, texts, yes) {
        title = heading
        paragraphs = texts
        confirmText = yes ? yes : "OK"
        returnTo = focusBack ? focusBack : Window.window ? Window.window.activeFocusItem : null
        visible = true
        cancel.forceActiveFocus()
    }
    function close(answer) {
        visible = false
        var back = returnTo
        if (answer) confirmed(); else declined()
        Qt.callLater(function() { if (back && back.enabled && back.visible) back.forceActiveFocus() })       // after the screen has re-enabled its button
    }

    Keys.onPressed: (event) => {
        if (event.key === Qt.Key_Escape) {
            close(false)
            event.accepted = true
        } else if (event.key === Qt.Key_Tab || event.key === Qt.Key_Backtab || event.key === Qt.Key_Left || event.key === Qt.Key_Right) {
            if (cancel.activeFocus) confirm.forceActiveFocus(); else cancel.forceActiveFocus()
            event.accepted = true
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
        objectName: "dlg_card"
        width: Math.min(Theme.dialogWidth, dialog.width - 2 * Theme.s32)
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
                objectName: "dlg_title"
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
                height: Math.min(words.implicitHeight, Math.max(Theme.touchSize, dialog.height - Theme.s16 - Theme.s16 - Theme.s24 - Theme.s24 - titleText.height - buttons.height - Theme.s12 - Theme.s12))
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
                            objectName: "dlg_p" + index
                            width: words.width
                            text: modelData.text
                            wrapMode: Text.WordWrap
                            font.pixelSize: Theme.bodySize
                            color: modelData.kind === "warn" ? Theme.warning : modelData.kind === "muted" ? Theme.muted : Theme.text
                        }
                    }
                }
            }
            ButtonRow {
                id: buttons
                width: content.width
                QuietButton {
                    id: cancel
                    objectName: "dlg_cancel"
                    text: dialog.cancelText
                    maxWidth: content.width
                    onClicked: dialog.close(false)
                }
                PrimaryButton {
                    id: confirm
                    objectName: "dlg_confirm"
                    text: dialog.confirmText
                    maxWidth: content.width
                    onClicked: dialog.close(true)
                }
            }
        }
    }
}
