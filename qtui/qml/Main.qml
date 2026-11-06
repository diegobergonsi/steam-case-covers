// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// The window: a left navigation and one screen at a time (docs/ui-guide.md). The screens here are placeholders; the real ones come in the next plans.
import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import "."

ApplicationWindow {
    id: win
    objectName: "window"
    width: Theme.windowWidth
    height: Theme.windowHeight
    minimumWidth: Theme.windowMinWidth
    minimumHeight: Theme.windowMinHeight
    visible: true
    title: qsTr("Steam Case Covers")
    color: Theme.bg

    readonly property int screenMs: Theme.dur(260)          // read by the tests
    readonly property int navWidth: Theme.navWidth

    Binding { target: Theme; property: "reduce"; value: shell.reduceEffects }
    onClosing: (close) => {                                       // never while Steam's artwork is being changed: it could be left half-done
        if (shell.apply.busy) {
            close.accepted = false
            if (!win.queued(qsTr("Please wait")))
                win.show(messages, [qsTr("Please wait"), [{"text": qsTr("Steam's artwork is being changed. Closing now could leave it half-done. Wait a few seconds, then close the window."), "kind": "main"}], "OK", "", true])
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
            objectName: "nav_highlight"
            x: Theme.s8
            width: nav.width - 2 * Theme.s8
            height: Theme.navHighlightHeight
            radius: Theme.radiusField
            color: Theme.raised
            y: Theme.navTop + shell.current * Theme.navRowHeight + (shell.current > 0 ? Theme.navHeadingHeight : 0) + Theme.navHighlightInset
            Behavior on y { NumberAnimation { duration: Theme.dur(200); easing.type: Easing.OutCubic } }
        }
        Text {
            objectName: "nav_title"
            x: Theme.s24
            y: Theme.s16
            width: nav.width - 2 * Theme.s24              // a wide font wraps the name onto a second line instead of running out of the menu
            wrapMode: Text.WordWrap
            maximumLineCount: 2
            text: qsTr("Steam Case Covers")
            color: Theme.text
            font.pixelSize: Theme.sectionSize
            font.bold: true
        }
        Row {
            objectName: "nav_languages"
            x: Theme.s24
            y: Theme.navFlagsY
            spacing: Theme.s8
            LanguageFlag {
                objectName: "language_en"
                source: usFlag
                name: "English"
                current: shell.language === "en"
                onActivated: shell.setLanguage("en")
            }
            LanguageFlag {
                objectName: "language_pt"
                source: brFlag
                name: "Português (Brasil)"
                current: shell.language === "pt-BR"
                onActivated: shell.setLanguage("pt-BR")
            }
        }
        Column {
            y: Theme.navTop
            width: nav.width
            Repeater {
                model: shell.steps
                delegate: Item {                                  // the row after Home also holds the heading of the way, above it
                    width: nav.width
                    height: Theme.navRowHeight + (index === 1 ? Theme.navHeadingHeight : 0)
                    Text {                                        // which way you are on: its name and how many steps it has
                        objectName: index === 1 ? "nav_flow" : ""
                        visible: index === 1
                        x: Theme.s24
                        width: nav.width - 2 * Theme.s24
                        height: Theme.navHeadingHeight
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                        text: shell.flowName + " \u00b7 " + qsTr("%n step|%n steps", "", shell.stepCount(shell.flow))
                        color: Theme.muted
                        font.pixelSize: Theme.smallSize
                        font.bold: true
                        Accessible.role: Accessible.Heading
                        Accessible.name: text
                    }
                    NavItem {
                        objectName: "nav_" + modelData.key
                        y: index === 1 ? Theme.navHeadingHeight : 0
                        width: nav.width
                        label: modelData.label
                        hint: modelData.hint
                        stepState: modelData.state
                        selected: index === shell.current
                        onActivated: shell.go(index)
                    }
                }
            }
        }
        NavLink {                                                 // footer: Discord, Ko-fi and updates
            objectName: "footer_discord"
            y: nav.height - 3 * Theme.navRowHeight - Theme.s8
            width: nav.width
            text: qsTr("Join our Discord")
            description: qsTr("Join our Discord server: ask for help, share ideas and report bugs. Opens in your web browser.")
            icon: discordIcon
            onActivated: shell.updates.openDiscord()
        }
        NavLink {
            objectName: "footer_kofi"
            y: nav.height - 2 * Theme.navRowHeight - Theme.s8
            width: nav.width
            text: qsTr("Support on Ko-fi")
            description: qsTr("Support the author on Ko-fi with a small donation. Optional, the app is free. Opens in your web browser.")
            icon: kofiIcon
            onActivated: shell.updates.openKofi()
        }
        NavLink {
            objectName: "footer_updates"
            y: nav.height - Theme.navRowHeight - Theme.s8
            width: nav.width
            text: shell.updates.checking ? qsTr("Checking\u2026") : qsTr("Check for updates")
            icon: updateIcon
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
                item.frozen = Qt.binding(function() { return shell.make.running && (screen.key === "game_list" || screen.key === "look" || screen.key === "hundred" || screen.key === "pick" || screen.key === "case") })
            }
            source: screen.key === "home" ? "HomeScreen.qml" : screen.key === "game_list" ? "GameListScreen.qml" : screen.key === "look" ? "LookScreen.qml" : screen.key === "pick" ? "GamesScreen.qml" : screen.key === "case" ? "CasesScreen.qml" : screen.key === "hundred" ? "HundredScreen.qml" : screen.key === "make" ? "MakeScreen.qml" : screen.key === "add" ? "AddScreen.qml" : "PlaceholderScreen.qml"
        }
    }

    Toast {                                                       // a short message from the shell, above the footer line of the screen
        id: toast
        objectName: "toast"
        x: win.navWidth + Theme.s32 + (win.width - win.navWidth - 2 * Theme.s32 - width) / 2
        y: win.height - Theme.s32 - Theme.controlHeight - Theme.s16 - height
    }
    Connections {
        target: shell
        function onToast(text) { toast.show(text) }
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
        var entry = {"dialog": dialog, "args": args, "link": link ? link : "", "cancel": cancel ? cancel : qsTr("Cancel")}
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
        function onFailed(text) { win.show(messages, [qsTr("Could not finish"), [{"text": text, "kind": "main"}], "OK", "", true]) }
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
        target: shell.owncase
        function onFailed(title, text) { win.show(messages, [title, [{"text": text, "kind": "main"}], "OK", "", true]) }
        function onNeedDialog(folder) { ownCaseDialog.currentFolder = shell.owncase.downloadsUrl; ownCaseDialog.open() }
    }
    FileDialog {                                                  // only when the desktop has no chooser of its own (see OwnCase.browse)
        id: ownCaseDialog
        title: qsTr("Choose your case file")
        nameFilters: [qsTr("PNG pictures (*.png)"), qsTr("All files (*)")]
        onAccepted: shell.owncase.useFileUrl(selectedFile.toString())
    }
    Connections {
        target: shell.updates
        function onMessage(title, paragraphs, ok, cancel, link) {
            win.show(messages, [title, paragraphs, ok, "", cancel === ""], link, cancel !== "" ? cancel : qsTr("Cancel"))
        }
    }
}
