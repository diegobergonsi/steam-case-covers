# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""The pictures the packaged app must carry (the build recipe steamcase-qt.spec bundles exactly these)."""
import os

REQUIRED_ASSETS = ("frame.png", "family_corner.png", "completion_overlay.png", "default_art.png", "icon.png", "discord.png", "kofi.png", "update.png", "flag_us.png", "flag_br.png", "christmas_overlay.png")

REQUIRED_CASES = ("cases.json", "ps3.png", "ps4.png", "ps5.png", "xbox360.png", "xboxone.png", "xboxseries.png", "switch.png", "switch2.png")      # in assets/cases


def missing_assets(assets_dir):
    """Names from REQUIRED_ASSETS, and "cases/<name>" for those of REQUIRED_CASES, that are not in `assets_dir`, sorted."""
    wanted = list(REQUIRED_ASSETS) + ["cases/" + n for n in REQUIRED_CASES]
    return sorted(n for n in wanted if not os.path.isfile(os.path.join(assets_dir, n)))
