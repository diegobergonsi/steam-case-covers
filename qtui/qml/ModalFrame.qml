// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// The frame of a window that covers the whole app and has to be answered or closed before anything else (ConfirmDialog, ManageGroup). It draws the dimmed
// layer that takes every click and every wheel turn, the card with its shadow, keeps the keyboard inside (Tab and Shift+Tab go round `stops`, and Left and
// Right too with `arrows`), says `escaped()` on Escape, and gives the keyboard back to where it was when the window closes. The owner sets the size of the
// card (`cardWidth`, `cardHeight`) and puts its words inside the frame; what it does, and when it is visible, is the owner's.
import QtQuick
import QtQuick.Effects
import "."

FocusScope {
    id: frame
    property string prefix: "dlg"                       // the objectName prefix of the card and its shadow, so two frames in one window can be told apart
    property real cardWidth: 0
    property real cardHeight: 0
    property var stops: function() { return [] }        // the items the keyboard goes round, in order (a function: the list may change while it is open)
    property bool arrows: false                         // Left and Right move the focus too (a row of buttons)
    property Item firstFocus: null                      // gets the focus when the window opens
    property Item focusBack: null                       // the item the keyboard goes back to, when the owner knows better than "what had the focus"
    property var returnTo: null
    signal escaped()
    default property alias content: card.data

    parent: Window.contentItem
    anchors.fill: parent
    z: 1
    Accessible.role: Accessible.Dialog

    function leave() {                                  // first take the focus off the controls: hiding a control that has it makes Qt print a warning
        if (Window.window) Window.window.contentItem.forceActiveFocus()
    }
    function step(delta) {                              // the focus moves between the controls and never leaves the window
        var list = stops().filter(function(i) { return i && i.visible && i.enabled })
        if (list.length === 0) return
        var at = 0
        for (var i = 0; i < list.length; i++) if (list[i].activeFocus) at = i
        list[(at + delta + list.length) % list.length].forceActiveFocus()
    }
    onVisibleChanged: {
        if (visible) {
            returnTo = focusBack ? focusBack : Window.window ? Window.window.activeFocusItem : null
            if (firstFocus) firstFocus.forceActiveFocus()
        } else {
            leave()
            var back = returnTo
            Qt.callLater(function() { if (back && back.enabled && back.visible) back.forceActiveFocus() })       // after the screen has re-enabled its button
        }
    }
    readonly property bool isModalFrame: true           // so a frame can tell another one (a question opened from a window) from the app behind
    property var lastInside: null                        // the last control of this window that had the keyboard
    // In the real window Tab does not always come to the keys handler below, so the focus can walk out to the app behind. This puts it back: a focus that
    // leaves goes to the first control, or to the last one when it left from the first (Shift+Tab). A question opened from this window is not "outside".
    Connections {
        target: frame.Window.window
        function onActiveFocusItemChanged() {
            if (!frame.visible || !frame.Window.window || !frame.Window.window.activeFocusItem) return
            var inside = true
            for (var n = frame.Window.window.activeFocusItem; n; n = n.parent) {
                if (n === frame) { inside = true; break }
                inside = false
                if (n.isModalFrame === true && n.visible) return
            }
            var list = frame.stops().filter(function(i) { return i && i.visible && i.enabled })
            if (inside) {
                frame.lastInside = frame.Window.window.activeFocusItem
                return
            }
            if (list.length === 0) return
            var from = frame.lastInside
            var target = from === list[0] && list.length > 1 ? list[list.length - 1] : list[0]
            Qt.callLater(function() { if (frame.visible) target.forceActiveFocus() })
        }
    }
    Keys.onPressed: (event) => {
        if (event.key === Qt.Key_Escape) {
            escaped()
            event.accepted = true
        } else if (event.key === Qt.Key_Tab || (arrows && event.key === Qt.Key_Right)) {
            step(1)
            event.accepted = true
        } else if (event.key === Qt.Key_Backtab || (arrows && event.key === Qt.Key_Left)) {
            step(-1)
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
    Rectangle {                                         // the shadow: a copy of the card's shape that carries nothing. The words must not be inside an effect layer:
        objectName: frame.prefix + "_shadow"            // drawn through a texture on a half pixel they blur, so the card below is a plain rectangle on whole pixels
        x: card.x
        y: card.y
        width: card.width
        height: card.height
        radius: Theme.radiusCard
        color: Theme.card
        layer.enabled: true
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: Theme.shadow
            shadowBlur: Theme.raisedShadowBlur
            shadowOpacity: Theme.cardShadowOpacity
            shadowVerticalOffset: Theme.raisedShadowOffset
        }
    }
    Rectangle {
        id: card
        objectName: frame.prefix + "_card"
        width: frame.cardWidth
        height: frame.cardHeight
        x: Math.round((frame.width - width) / 2)
        y: Math.round(Math.max(Theme.s16, (frame.height - height) / 2))
        color: Theme.card
        radius: Theme.radiusCard
    }
}
