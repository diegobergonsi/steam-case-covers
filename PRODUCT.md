# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Non-technical Steam players on Windows, macOS (Apple Silicon, best effort) and Steam Deck / Linux. They want their library to look like a shelf of boxed console games. They download one file, click through three steps, and never open a terminal. A command-line interface exists for tinkerers but is not the primary audience.

## Product Purpose

steam-case-covers gives every game in a Steam library a "physical copy" case cover: the game's own portrait art inside a blue box with a Steam banner and platform badges, installed as custom artwork. Success is a user going from download to a transformed library with no confusion and no risk to their Steam data.

## Positioning

Everything runs on the user's computer: no login, no API key, no uploads. Art comes from Steam's own servers; covers are built and stay local. Free, open source (GPL-3.0-or-later), not affiliated with Valve.

## Operating Context

Desktop app (tkinter window with three steps, custom Canvas widgets in `widgets.py`), packaged with PyInstaller for three OSes and released by GitHub Actions. Works against the user's real Steam folder (`userdata/<id>/config/grid`), supports multiple accounts via an account picker, can Reset including art from other sources. Must work on Steam Deck screens, high-DPI displays and small screens. Handheld users (Steam Deck and similar) really do use the touchscreen, so touch is a first-class input: targets of 44px or more, no hover-only behavior, and drag-to-scroll.

## Capabilities and Constraints

- Local only: no login, no API key, no uploads.
- Image work uses Pillow; window stays tkinter with custom widgets.
- Core visual asset: `assets/frame.png` (600x900 case frame with transparent art window).
- Unsigned binaries (Windows SmartScreen and macOS Gatekeeper warnings are documented in the README).
- Trademark caution: Steam and Windows belong to their owners; see THIRD_PARTY.md.

## Brand Commitments

- App icon is original artwork, deliberately without the Steam logo. The Steam logo appears only inside the covers.
- Friendly, plain-English voice for non-technical users; honest about limits (best-effort macOS, unsigned apps).

## Evidence on Hand

Real assets in `assets/`: `preview.png`, `screenshot.png`, `steam-library.png`, icon set. Releases v1.0.0 and v1.1.0 on GitHub. A colleague confirmed an earlier Windows build works (second-hand). No user testimonials or download statistics exist; do not invent any.

## Product Principles

1. Three steps, no terminal: nothing should require technical knowledge.
2. Safe by default: never touch the user's Steam data in ways they cannot undo.
3. Local and private: no accounts, no uploads, no network beyond Steam's art servers.
4. Honest about what was and was not tested per platform.
5. The covers are the star; the app window stays quiet and out of the way.

## Accessibility & Inclusion

Keyboard use, touch use on handhelds, high-DPI layout and small-screen (Steam Deck) handling must keep working.
