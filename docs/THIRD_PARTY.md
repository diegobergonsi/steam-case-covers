# Third-party material and trademarks

This project is **not affiliated with, endorsed by, or sponsored by Valve Corporation, Microsoft, or any game publisher.**

## Trademarks
- **Steam** and the Steam logo are trademarks and/or registered trademarks of Valve Corporation.
- **Windows** and the Windows logo are trademarks of the Microsoft group of companies.
- **Linux** is a trademark of Linus Torvalds. The penguin is "Tux".
- **Discord** and its logo are trademarks of Discord Inc. The mark appears only as the button in the window's header that links to this project's Discord server; it does not mean that Discord endorses this project.

These marks appear in `assets/frame.png` only to mimic a physical box and show platform support. They remain the property of their owners. If you are a rights holder and want something changed, open an issue.

`assets/family_corner.png` is a green corner with a three-person icon drawn to resemble the Family icon in Steam's settings. It is original artwork and is not Valve's file.

`assets/halloween_overlay.png` (source: `tools/src/halloween.svg`) holds the decorations of the Halloween case theme: a cobweb, two spiders and a pumpkin. It is original artwork drawn for this project and released under the project's licence; it is not taken from any game or brand.

`assets/completion_overlay.png` holds the rosette and the "100% Complete" ribbon drawn on covers of games where every achievement is unlocked. The rosette is an original drawing inspired by the look of Steam's old achievement ribbon; it is not Valve's artwork. The file is built by `tools/build_completion_overlay.py` with the Nunito Sans font credited below.

`assets/default_art.png` (source: `tools/src/default_art.svg`) is original artwork drawn for this project and released under the project's licence. It is not taken from any game and is only used to preview the case colour.

## Included files
| File | Source | License |
|---|---|---|
| `tools/src/steam_logo.svg` | SVG Repo ("steam" icon) | **License not verified.** The logo itself is Valve's trademark. If a rights holder objects, it will be replaced. |
| `tools/src/discord.svg` (rendered to `assets/discord.png`) | Simple Icons 13.0.0 ("Discord" icon) | CC0 1.0 (public domain dedication). The logo itself is Discord's trademark; see Trademarks above. |
| `tools/src/tux.svg` | KDE Breeze icon theme (`preferences-system-linux`), from the Arch Linux `breeze-icons` package | LGPL-3.0-or-later (package metadata also lists LGPL-2.1-only). Text: `tools/src/LICENSE-LGPL-3.0.txt` |
| `tools/src/fonts/NunitoSans.ttf` | Nunito Sans, Google Fonts | SIL Open Font License 1.1 (`tools/src/fonts/OFL.txt`) |

`assets/icon.*` (the app icon, source in `tools/src/icon.svg`) is original artwork released under the same license as the code (GPL-3.0-or-later). It deliberately does not use the Steam logo.

The font and the SVG sources are only used by `tools/build_frame.py`, `tools/build_icon.py`, `tools/build_default_art.py` and `tools/build_completion_overlay.py` to render `assets/frame.png`, the icons, `assets/default_art.png` and `assets/completion_overlay.png`. They are not needed to run the app.

## Game artwork
The preview image at the top of the README (`assets/preview.png`) shows covers of a few games (SnowRunner, Coral Island, Clair Obscur: Expedition 33, Fallout 4 and V Rising), the screenshot of the app window (`assets/screenshot.png`) shows the same five, and the two screenshots of a Steam library further up (`assets/library-100.png` and `assets/library-mixed.png`) show covers of about fifty games, only to show what the app produces. That artwork, and the games' names and logos, belong to their publishers and developers. They are not covered by this project's license. If a rights holder objects, the image will be removed.

Apart from those images, no game artwork is included. Covers are built on your own machine from the portrait images Steam serves for games in your own library. Generated covers contain publishers' artwork: use them for personal use and do not redistribute them.

## Release builds
The downloadable apps bundle Python (PSF License), Pillow (HPND License) and Qt for Python (PySide6 and the Qt libraries, LGPL-3.0: the Qt libraries stay separate files you can replace; their licence text and source are at https://www.qt.io/ and https://code.qt.io/), and are built with PyInstaller (GPL-2.0 with a bootloader exception that allows distributing the built apps under other licenses).
