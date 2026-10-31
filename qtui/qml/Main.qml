// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// The window: a left navigation and one screen at a time (docs/ui-guide.md). The screens here are placeholders; the real ones come in the next plans.
import QtQuick
import QtQuick.Controls
import "."

ApplicationWindow {
    id: win
    objectName: "window"
    width: Theme.windowWidth
    height: Theme.windowHeight
    minimumWidth: Theme.windowMinWidth
    minimumHeight: Theme.windowMinHeight
    visible: true
    title: "Steam Case Covers"
    color: Theme.bg

    readonly property int screenMs: Theme.dur(260)          // read by the tests
    readonly property int navWidth: Theme.navWidth

    Binding { target: Theme; property: "reduce"; value: shell.reduceEffects }
    onClosing: (close) => {                                       // never while Steam's artwork is being changed: it could be left half-done
        if (shell.apply.busy) {
            close.accepted = false
            if (!win.queued("Please wait"))
                win.show(messages, ["Please wait", [{"text": "Steam's artwork is being changed. Closing now could leave it half-done. Wait a few seconds, then close the window.", "kind": "main"}], "OK", "", true])
        }
    }
    Timer { interval: 1500; repeat: true; running: true; onTriggered: shell.poll() }       // notices the saved game list and games page

    Rectangle {                                                   // the navigation
        id: nav
        objectName: "nav"
        width: win.navWidth
        height: parent.height
        color: Theme.navBg

        Rectangle {                                               // the highlight glides to the chosen step
            x: Theme.s8
            width: nav.width - 2 * Theme.s8
            height: Theme.navHighlightHeight
            radius: Theme.radiusField
            color: Theme.raised
            y: Theme.navTop + shell.current * Theme.navRowHeight + Theme.navHighlightInset
            Behavior on y { NumberAnimation { duration: Theme.dur(200); easing.type: Easing.OutCubic } }
        }
        Text {
            x: Theme.s24
            y: Theme.s24
            text: "Case Covers"
            color: Theme.text
            font.pixelSize: Theme.sectionSize
            font.bold: true
        }
        Column {
            y: Theme.navTop
            width: nav.width
            Repeater {
                model: shell.steps
                delegate: NavItem {
                    objectName: "nav_" + modelData.key
                    width: nav.width
                    label: modelData.label
                    hint: modelData.hint
                    stepState: modelData.state
                    selected: index === shell.current
                    onActivated: shell.go(index)
                }
            }
        }
        NavLink {                                                 // footer: Discord and updates
            objectName: "footer_discord"
            y: nav.height - Theme.navRowHeight - Theme.navRowHeight - Theme.s8
            width: nav.width
            text: "Join our Discord"
            description: "Join our Discord server: ask for help, share ideas and report bugs. Opens in your web browser."
            icon: discordIcon
            onActivated: shell.updates.openDiscord()
        }
        NavLink {
            objectName: "footer_updates"
            y: nav.height - Theme.navRowHeight - Theme.s8
            width: nav.width
            text: shell.updates.checking ? "Checking\u2026" : "Check for updates"
            onActivated: shell.updates.check()
        }
    }

    Item {                                                        // the screen: fades and slides in when the step changes
        id: screen
        x: win.navWidth + Theme.s32
        width: parent.width - win.navWidth - 2 * Theme.s32
        height: parent.height
        readonly property int index: shell.current
        readonly property string key: shell.steps[shell.current].key
        onIndexChanged: enter.restart()
        ParallelAnimation {
            id: enter
            NumberAnimation { target: screen; property: "opacity"; from: 0; to: 1; duration: Theme.dur(260) }
            NumberAnimation { target: screen; property: "x"; from: win.navWidth + Theme.s32 + Theme.slideOffset; to: win.navWidth + Theme.s32; duration: Theme.dur(260); easing.type: Easing.OutCubic }
        }
        Loader {
            anchors.fill: parent
            // the choices of the earlier steps are frozen while the covers are made, as in the old window (the run has its own copy of them)
            onLoaded: {
                item.stepKey = Qt.binding(function() { return screen.key })
                item.frozen = Qt.binding(function() { return shell.make.running && (screen.key === "game_list" || screen.key === "look" || screen.key === "hundred") })
            }
            source: screen.key === "home" ? "HomeScreen.qml" : screen.key === "game_list" ? "GameListScreen.qml" : screen.key === "look" ? "LookScreen.qml" : screen.key === "hundred" ? "HundredScreen.qml" : screen.key === "make" ? "MakeScreen.qml" : screen.key === "add" ? "AddScreen.qml" : "PlaceholderScreen.qml"
        }
    }

    // Two dialogs are never open at once: the window's own (the questions of Apply, the answers of the update check) take turns.
    property Item lastFocus: null                                 // where the keyboard was before a question, for the way back
    onActiveFocusItemChanged: if (activeFocusItem && !String(activeFocusItem.objectName).match(/_dlg_/)) lastFocus = activeFocusItem
    property var waiting: []
    function present(entry) {                                     // the link and the label of Cancel belong to the box, set when it is shown
        if (entry.dialog === messages) messages.link = entry.link
        entry.dialog.cancelText = entry.cancel
        entry.dialog.ask.apply(entry.dialog, entry.args)
    }
    function show(dialog, args, link, cancel) {
        var entry = {"dialog": dialog, "args": args, "link": link ? link : "", "cancel": cancel ? cancel : "Cancel"}
        if (applyDialog.visible || messages.visible) waiting.push(entry); else present(entry)
    }
    function queued(title) {
        if (messages.visible && messages.title === title) return true
        for (var i = 0; i < waiting.length; i++) if (waiting[i].args[0] === title) return true
        return false
    }
    function next() {
        if (!applyDialog.visible && !messages.visible && waiting.length > 0) present(waiting.shift())
    }
    ConfirmDialog {                                               // the questions of Apply: add to Steam, restore, reset (wherever the user is)
        id: applyDialog
        objectName: "apply_dialog"
        prefix: "apply_dlg"
        focusBack: win.lastFocus
        onConfirmed: shell.apply.confirm()
        onDeclined: shell.apply.decline()
        onAlternated: shell.apply.confirmAlternate()
        onVisibleChanged: if (!visible) Qt.callLater(win.next)            // after the answer of this box has been handled
    }
    ConfirmDialog {                                               // answers of the update check and of the Discord link, and errors
        id: messages
        objectName: "main_dialog"
        prefix: "main_dlg"
        property string link: ""
        onConfirmed: if (link !== "") shell.updates.openLink(link)
        onVisibleChanged: if (!visible) Qt.callLater(win.next)            // after the answer of this box has been handled
    }
    Connections {
        target: shell.apply
        function onConfirmNeeded(title, paragraphs, go, alt) { win.show(applyDialog, [title, paragraphs, go, alt]) }
        function onFailed(text) { win.show(messages, ["Could not finish", [{"text": text, "kind": "main"}], "OK", "", true]) }
    }
    Connections {
        target: shell.library
        function onFailed(title, text) { win.show(messages, [title, [{"text": text, "kind": "main"}], "OK", "", true]) }
    }
    Connections {
        target: shell.make
        function onFailed(title, text) { win.show(messages, [title, [{"text": text, "kind": "main"}], "OK", "", true]) }
    }
    Connections {
        target: shell.updates
        function onMessage(title, paragraphs, ok, cancel, link) {
            win.show(messages, [title, paragraphs, ok, "", cancel === ""], link, cancel !== "" ? cancel : "Cancel")
        }
    }
}
