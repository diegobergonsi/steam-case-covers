// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// A row of small pictures of covers (the first covers of a run), wrapping onto more rows when the window is narrow. `model` is a list of file URLs;
// each picture is named `prefix` + its number for the tests and the screen readers. Not shown while the list is empty.
import QtQuick
import "."

Flow {
    id: thumbs
    property var model: []
    property string prefix: ""
    visible: model.length > 0
    spacing: Theme.s8
    Repeater {
        model: thumbs.model
        delegate: Image {
            objectName: thumbs.prefix + index
            width: Theme.thumbWidth
            height: Theme.thumbHeight
            source: modelData
            sourceSize.width: Theme.thumbPixels
            fillMode: Image.PreserveAspectFit
            asynchronous: true
            cache: false                                  // a cover made again under the same name must show the new picture
            Accessible.role: Accessible.Graphic
            Accessible.name: qsTr("Cover %1").arg(index + 1)
        }
    }
}
