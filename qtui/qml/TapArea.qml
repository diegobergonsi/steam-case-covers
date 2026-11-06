// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// The part of a small control that reacts to a tap: at least Theme.touchMin wide and high, centred on the control, so a finger can hit a control that is drawn smaller
// (the "i", a language flag). A MouseArea in every other way: put it inside the control.
import QtQuick
import "."

MouseArea {
    width: Math.max(parent.width, Theme.touchMin)
    height: Math.max(parent.height, Theme.touchMin)
    x: (parent.width - width) / 2
    y: (parent.height - height) / 2
}
