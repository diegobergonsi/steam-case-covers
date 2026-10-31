// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
// A section of a screen: a raised card with a soft shadow. Put the section's heading and controls inside it.
import QtQuick
import QtQuick.Effects

Rectangle {
    color: Theme.card
    radius: Theme.radiusCard
    layer.enabled: true
    layer.effect: MultiEffect {
        shadowEnabled: true
        shadowColor: Theme.shadow
        shadowBlur: Theme.cardShadowBlur
        shadowOpacity: Theme.cardShadowOpacity
        shadowVerticalOffset: Theme.cardShadowOffset
    }
}
