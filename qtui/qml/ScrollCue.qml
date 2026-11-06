// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// The vertical scroll bar every scrolling page and list uses: always on while there is more to scroll to (so nobody has to guess it scrolls), gone when everything fits.
// Use it as `ScrollBar.vertical: ScrollCue {}` on a Flickable or ListView.
import QtQuick
import QtQuick.Controls
import "."

ScrollBar {
    policy: size < 1 ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
    implicitWidth: Theme.s8
    contentItem: Rectangle { radius: width / 2; color: Theme.edge }
    background: Rectangle { radius: width / 2; color: Theme.card }
}
