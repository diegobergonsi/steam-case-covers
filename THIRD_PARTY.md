# Third-party material and trademarks

This project is **not affiliated with, endorsed by, or sponsored by Valve Corporation, Microsoft, or any game publisher.**

## Trademarks
- **Steam** and the Steam logo are trademarks and/or registered trademarks of Valve Corporation.
- **Windows** and the Windows logo are trademarks of the Microsoft group of companies.
- **Linux** is a trademark of Linus Torvalds. The penguin is "Tux".

These marks appear in `assets/frame.png` only to mimic a physical box and show platform support. They remain the property of their owners. If you are a rights holder and want something changed, open an issue.

## Included files
| File | Source | License |
|---|---|---|
| `tools/src/steam_logo.svg` | SVG Repo ("steam" icon) | **License not verified.** The logo itself is Valve's trademark. If a rights holder objects, it will be replaced. |
| `tools/src/tux.svg` | KDE Breeze icon theme (`preferences-system-linux`), from the Arch Linux `breeze-icons` package | LGPL-3.0-or-later (package metadata also lists LGPL-2.1-only). Text: `tools/src/LICENSE-LGPL-3.0.txt` |
| `tools/src/fonts/NunitoSans.ttf` | Nunito Sans, Google Fonts | SIL Open Font License 1.1 (`tools/src/fonts/OFL.txt`) |

`assets/icon.*` (the app icon, source in `tools/src/icon.svg`) is original artwork released under the same license as the code (GPL-3.0-or-later). It deliberately does not use the Steam logo.

The font and the SVG sources are only used by `tools/build_frame.py` and `tools/build_icon.py` to render `assets/frame.png` and the icons. They are not needed to run the app.

## Game artwork
The preview image at the top of the README (`assets/preview.png`) shows covers of a few games (SnowRunner, Coral Island, Clair Obscur: Expedition 33, Fallout 4 and V Rising) only to show what the app produces. That artwork, and the games' names and logos, belong to their publishers and developers. They are not covered by this project's license. If a rights holder objects, the image will be removed.

Apart from that image, no game artwork is included. Covers are built on your own machine from the portrait images Steam serves for games in your own library. Generated covers contain publishers' artwork: use them for personal use and do not redistribute them.

## Release builds
The downloadable apps bundle Python (PSF License), Pillow (HPND License) and Tcl/Tk (BSD-style license), and are built with PyInstaller (GPL-2.0 with a bootloader exception that allows distributing the built apps under other licenses).
