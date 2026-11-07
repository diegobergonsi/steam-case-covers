// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// The window to manage one group (opened by the Manage button of Home): rename it, tick or untick its games, delete it. It covers the app like a question does
// (one window in all). Escape closes it without saving; Tab stays inside; the focus goes back to the button that opened it. What it does is in `shell.manage`.
import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import "."

FocusScope {
    id: dialog
    readonly property var manage: shell.manage
    property var returnTo: null                         // the item that had the focus before, so the keyboard comes back to it

    parent: Window.contentItem
    anchors.fill: parent
    z: 1
    visible: manage.isOpen
    Accessible.role: Accessible.Dialog
    Accessible.name: qsTr("Manage “%1”").arg(manage.title)

    onVisibleChanged: {
        if (visible) {
            returnTo = Window.window ? Window.window.activeFocusItem : null
            search.forceActiveFocus()
        } else {
            if (Window.window) Window.window.contentItem.forceActiveFocus()
            var back = returnTo
            Qt.callLater(function() { if (back && back.enabled && back.visible) back.forceActiveFocus() })
        }
    }
    function leave() {                                  // first take the focus off the buttons: hiding a button that has it makes Qt print a warning
        if (Window.window) Window.window.contentItem.forceActiveFocus()
    }
    function step(delta) {                              // the focus moves between the controls and never leaves the window
        var list = [nameField, renameButton, search, list, deleteButton, cancelButton, saveButton].filter(function(i) { return i.visible && i.enabled })
        var at = 0
        for (var i = 0; i < list.length; i++) if (list[i].activeFocus) at = i
        list[(at + delta + list.length) % list.length].forceActiveFocus()
    }
    Keys.onPressed: (event) => {
        if (event.key === Qt.Key_Escape) {
            leave()
            manage.cancel()
            event.accepted = true
        } else if (event.key === Qt.Key_Tab) {
            step(1)
            event.accepted = true
        } else if (event.key === Qt.Key_Backtab) {
            step(-1)
            event.accepted = true
        }
    }

    Rectangle {                                         // the dimmed window behind; it takes every click
        anchors.fill: parent
        color: Theme.shadow
        opacity: Theme.scrimOpacity
    }
    MouseArea {
        anchors.fill: parent
        onWheel: (wheel) => wheel.accepted = true
    }
    Rectangle {                                         // the shadow, apart from the words (see ConfirmDialog)
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
        objectName: "manage_card"
        width: Math.min(Theme.manageWidth, dialog.width - 2 * Theme.s32)
        height: Math.min(content.implicitHeight + 2 * Theme.s24, dialog.height - 2 * Theme.s16)
        x: Math.round((dialog.width - width) / 2)
        y: Math.round((dialog.height - height) / 2)
        color: Theme.card
        radius: Theme.radiusCard
        Flickable {                                     // on a very short window the card scrolls; its buttons are always the last thing
            anchors.fill: parent
            anchors.margins: Theme.s24
            contentWidth: width
            contentHeight: content.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            Column {
                id: content
                width: parent.width
                spacing: Theme.s12
                Text {
                    objectName: "manage_title"
                    width: parent.width
                    text: qsTr("Manage “%1”").arg(dialog.manage.title)
                    textFormat: Text.PlainText                  // a name is the player's own words, never markup
                    wrapMode: Text.WrapAtWordBoundaryOrAnywhere
                    color: Theme.text
                    font.pixelSize: Theme.sectionSize
                    font.bold: true
                }
                Row {
                    width: parent.width
                    spacing: Theme.s8
                    TextField {
                        id: nameField
                        objectName: "manage_name"
                        width: parent.width - renameButton.width - Theme.s8
                        height: Theme.touchMin
                        text: dialog.manage.name
                        color: Theme.text
                        font.pixelSize: Theme.bodySize
                        selectByMouse: true
                        Accessible.name: qsTr("Group name")
                        background: Rectangle {
                            radius: Theme.radiusField
                            color: Theme.bg
                            border.width: parent.activeFocus ? Theme.focusRing : Theme.hairline
                            border.color: parent.activeFocus ? Theme.accent : Theme.edge
                        }
                        onTextEdited: dialog.manage.name = text
                        onAccepted: if (renameButton.enabled) dialog.manage.rename()
                    }
                    QuietButton {
                        id: renameButton
                        objectName: "manage_rename"
                        text: qsTr("Rename")
                        enabled: dialog.manage.name.trim() !== "" && dialog.manage.name !== dialog.manage.title
                        onClicked: dialog.manage.rename()
                    }
                }
                Text {
                    objectName: "manage_error"
                    width: parent.width
                    visible: dialog.manage.error !== ""
                    text: dialog.manage.error
                    wrapMode: Text.WordWrap
                    color: Theme.error
                    font.pixelSize: Theme.bodySize
                }
                Text {
                    objectName: "manage_count"
                    width: parent.width
                    text: qsTr("%n game ticked|%n games ticked", "", dialog.manage.tickedCount)
                    color: Theme.muted
                    font.pixelSize: Theme.bodySize
                }
                TextField {
                    id: search
                    objectName: "manage_search"
                    width: parent.width
                    height: Theme.touchMin
                    placeholderText: qsTr("Search by name…")
                    placeholderTextColor: Theme.faint
                    text: dialog.manage.query
                    color: Theme.text
                    font.pixelSize: Theme.bodySize
                    selectByMouse: true
                    Accessible.name: qsTr("Search your games by name")
                    background: Rectangle {
                        radius: Theme.radiusField
                        color: Theme.bg
                        border.width: parent.activeFocus ? Theme.focusRing : Theme.hairline
                        border.color: parent.activeFocus ? Theme.accent : Theme.edge
                    }
                    onTextEdited: dialog.manage.query = text
                }
                StatusLine {
                    objectName: "manage_status"
                    width: parent.width
                    visible: dialog.manage.loading || !dialog.manage.canSave
                    text: dialog.manage.loading ? qsTr("Loading your games…") : qsTr("Your games could not be listed, so this group cannot be changed now.")
                    kind: dialog.manage.loading ? "wait" : "error"
                }
                ListView {
                    id: list
                    objectName: "manage_list"
                    width: parent.width
                    height: Theme.manageRows * Theme.touchMin
                    clip: true
                    model: dialog.manage.model
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollCue { objectName: "manage_scrollbar" }
                    activeFocusOnTab: true
                    keyNavigationEnabled: true
                    highlightMoveDuration: Theme.dur(90)
                    highlight: Rectangle {
                        radius: Theme.radiusField
                        color: "transparent"
                        border.width: list.activeFocus ? Theme.focusRing : 0
                        border.color: Theme.text
                    }
                    Accessible.role: Accessible.List
                    Accessible.name: qsTr("Games of this group")
                    onActiveFocusChanged: if (activeFocus && currentIndex < 0 && count > 0) currentIndex = 0
                    Keys.onPressed: (event) => {
                        if ((event.key === Qt.Key_Space || event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && list.currentItem) {
                            if (!event.isAutoRepeat) dialog.manage.toggle(list.currentItem.rowAppid)
                            event.accepted = true
                        }
                    }
                    delegate: GameRow {
                        objectName: "manage_game_" + model.appid
                        width: list.width
                        appid: model.appid
                        name: model.name
                        selected: model.selected
                        tag: model.tag === "" ? "" : model.selected ? qsTr("moves from %1").arg(model.tag) : qsTr("in %1").arg(model.tag)
                        onToggled: { list.currentIndex = index; list.forceActiveFocus(); dialog.manage.toggle(model.appid) }
                    }
                }
                Text {
                    objectName: "manage_warning"
                    width: parent.width
                    visible: dialog.manage.warning !== ""
                    text: dialog.manage.warning
                    wrapMode: Text.WordWrap
                    color: Theme.warning
                    font.pixelSize: Theme.bodySize
                }
                Text {
                    objectName: "manage_notice"
                    width: parent.width
                    wrapMode: Text.WordWrap
                    color: Theme.muted
                    font.pixelSize: Theme.bodySize
                    text: qsTr("Changes show on your covers the next time you make covers, with “Same case” or “Pick games”. Nothing on Steam changes until then.")
                }
                ButtonRow {
                    QuietButton {
                        id: deleteButton
                        objectName: "manage_delete"
                        text: qsTr("Delete group")
                        onClicked: deleteDialog.ask(qsTr("Delete “%1”?").arg(dialog.manage.title),
                                                    [{text: qsTr("The group is removed. Covers already on Steam stay there. Your games are not touched."), kind: "main"}],
                                                    qsTr("Delete group"))
                    }
                    QuietButton {
                        id: cancelButton
                        objectName: "manage_cancel"
                        text: qsTr("Cancel")
                        onClicked: { dialog.leave(); dialog.manage.cancel() }
                    }
                    PrimaryButton {
                        id: saveButton
                        objectName: "manage_save"
                        text: qsTr("Save")
                        enabled: dialog.manage.canSave
                        onClicked: { dialog.leave(); dialog.manage.save() }
                    }
                }
            }
        }
    }
    ConfirmDialog {                                     // deleting asks first; the safe button (Cancel) has the focus
        id: deleteDialog
        objectName: "manage_delete_dialog"
        prefix: "manage_delete_dlg"
        z: 2
        focusBack: deleteButton
        onConfirmed: { dialog.leave(); dialog.manage.deleteGroup() }
    }
}
