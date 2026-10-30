// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// A slider whose track shows what moving it does (colours come from Python). The owner keeps the value: bind `value`, and set it from `moved`.
// Mouse and touch drag, a click on the track jumps; arrows move by 1, Page keys by 10, Home and End jump to the ends.
import QtQuick
import "."

Item {
    id: slider
    property string label: ""
    property int from: 0
    property int to: 100
    property int value: 0
    property var stops: []                              // colours along the track, as "#rrggbb" strings
    signal moved(int value)

    readonly property real handleSize: Theme.touchSize
    readonly property real span: Math.max(Theme.minSpan, width - handleSize)
    implicitHeight: handleSize
    activeFocusOnTab: true
    Accessible.role: Accessible.Slider
    Accessible.name: label
    Accessible.description: value + " (" + from + " to " + to + ")"
    Accessible.onIncreaseAction: slider.step(1)
    Accessible.onDecreaseAction: slider.step(-1)

    function clampValue(v) { return Math.max(from, Math.min(to, Math.round(v))) }
    function step(delta) { var v = clampValue(value + delta); if (v !== value) moved(v) }
    function pointTo(x) {
        var v = clampValue(from + (x - handleSize / 2) / span * (to - from))
        if (v !== value) moved(v)
    }

    Canvas {                                            // the track
        id: track
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        height: Theme.sliderTrack
        onWidthChanged: requestPaint()
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            var r = height / 2
            ctx.beginPath()
            ctx.moveTo(r, 0)
            ctx.lineTo(width - r, 0)
            ctx.arc(width - r, r, r, -Math.PI / 2, Math.PI / 2)
            ctx.lineTo(r, height)
            ctx.arc(r, r, r, Math.PI / 2, 3 * Math.PI / 2)
            ctx.closePath()
            var g = ctx.createLinearGradient(0, 0, width, 0)
            var n = slider.stops.length
            for (var i = 0; i < n; i++)
                g.addColorStop(n === 1 ? 0 : i / (n - 1), slider.stops[i])
            ctx.fillStyle = n > 0 ? g : Theme.raised
            ctx.fill()
        }
        Connections { target: slider; function onStopsChanged() { track.requestPaint() } }
    }
    Rectangle {                                         // keyboard focus ring, around the whole control
        anchors.fill: parent
        radius: height / 2
        color: "transparent"
        border.width: slider.activeFocus ? Theme.focusRing : 0
        border.color: Theme.text
    }
    Rectangle {                                         // the handle
        id: handle
        width: slider.handleSize
        height: slider.handleSize
        radius: width / 2
        x: (slider.value - slider.from) / Math.max(Theme.minSpan, slider.to - slider.from) * slider.span
        anchors.verticalCenter: parent.verticalCenter
        color: Theme.text
        border.width: Theme.focusRing
        border.color: Theme.bg
    }
    MouseArea {
        id: area
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        property bool dragging: false
        property bool touch: false
        property real pressX: 0
        // a mouse jumps and drags from anywhere; a finger drags only the handle and taps to jump, so a swipe that starts on the track scrolls the page
        onPressed: (mouse) => {
            slider.forceActiveFocus()
            touch = mouse.source !== Qt.MouseEventNotSynthesized
            pressX = mouse.x
            dragging = !touch || Math.abs(mouse.x - (handle.x + handle.width / 2)) <= handle.width / 2
            preventStealing = dragging
            if (!touch) slider.pointTo(mouse.x)
        }
        onPositionChanged: (mouse) => { if (pressed && dragging) slider.pointTo(mouse.x) }
        onReleased: (mouse) => {
            if (touch && !dragging && Math.abs(mouse.x - pressX) < Theme.s8) slider.pointTo(mouse.x)
            dragging = false
            preventStealing = false
        }
        onCanceled: { dragging = false; preventStealing = false }
    }
    Keys.onPressed: (event) => {
        var k = event.key
        if (k === Qt.Key_Right || k === Qt.Key_Up) slider.step(1)
        else if (k === Qt.Key_Left || k === Qt.Key_Down) slider.step(-1)
        else if (k === Qt.Key_PageUp) slider.step(10)
        else if (k === Qt.Key_PageDown) slider.step(-10)
        else if (k === Qt.Key_Home) slider.step(from - value)
        else if (k === Qt.Key_End) slider.step(to - value)
        else return
        event.accepted = true
    }
}
