# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""The pictures the packaged app must carry (the build recipe steamcase-qt.spec bundles exactly these)."""
import os

REQUIRED_ASSETS = ("frame.png", "family_corner.png", "completion_overlay.png", "default_art.png", "icon.png", "discord.png", "halloween_overlay.png")


def missing_assets(assets_dir):
    """Names from REQUIRED_ASSETS that are not in `assets_dir`, sorted."""
    return sorted(n for n in REQUIRED_ASSETS if not os.path.isfile(os.path.join(assets_dir, n)))
