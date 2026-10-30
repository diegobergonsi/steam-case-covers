// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// The sample cover, drawn by the engine (image://preview/...). While the next picture loads, the old one stays: nothing blinks while a slider is dragged.
import QtQuick
import QtQuick.Effects
import "."

Item {
    id: card
    property url source
    readonly property int status: back.status
    readonly property bool showing: front.status === Image.Ready
    width: Theme.previewWidth
    height: Theme.previewHeight

    Image {                                             // loads the new picture out of sight
        id: back
        visible: false
        source: card.source
        asynchronous: true
        cache: false
        sourceSize: Qt.size(card.width, card.height)
        onStatusChanged: if (status === Image.Ready) front.source = source
    }
    Image {                                             // what is shown: always a finished picture
        id: front
        anchors.fill: parent
        cache: false
        sourceSize: Qt.size(card.width, card.height)
        layer.enabled: true
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: Theme.shadow
            shadowBlur: Theme.cardShadowBlur
            shadowOpacity: Theme.cardShadowOpacity
            shadowVerticalOffset: Theme.cardShadowOffset
        }
    }
}
