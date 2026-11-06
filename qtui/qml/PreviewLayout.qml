// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// The layout of the screens that show a sample cover (Look, 100% games, Case, Make): the preview at the left with the sections beside it, or above them
// when the window is narrow. Put the sections inside it. Something that sits under the preview (the caption of the 100% games) goes in `underPreview`,
// and the height it takes, gap included, in `underHeight`, so the sections below it start in the right place.
import QtQuick
import "."

Item {
    id: layout
    property alias previewName: preview.objectName         // the objectName of the PreviewCard: each screen has its own
    property url source
    property real underHeight: 0
    default property alias sections: column.data
    property alias underPreview: under.data
    readonly property bool narrow: width < Theme.previewWidth + Theme.s24 + Theme.sectionMinWidth
    readonly property real previewBlock: Theme.previewHeight + underHeight

    width: parent.width
    implicitHeight: narrow ? previewBlock + Theme.s24 + column.implicitHeight : Math.max(previewBlock, column.implicitHeight)
    height: implicitHeight

    PreviewCard {
        id: preview
        x: layout.narrow ? Math.max(0, (layout.width - width) / 2) : 0
        source: layout.source
    }
    Item {
        id: under
        x: preview.x
        y: preview.height
        width: preview.width
        height: layout.underHeight
    }
    Column {
        id: column
        x: layout.narrow ? 0 : preview.width + Theme.s24
        y: layout.narrow ? layout.previewBlock + Theme.s24 : 0
        width: layout.width - x
        spacing: Theme.s24
    }
}
