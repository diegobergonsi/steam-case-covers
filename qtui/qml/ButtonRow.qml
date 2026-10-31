// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// Buttons that reach the same goal sit in one row (rule 11 of the guide); on a narrow window the row wraps instead of overflowing.
import QtQuick
import "."

Flow {
    width: parent ? parent.width : 0
    spacing: Theme.s8
}
