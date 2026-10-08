# Changelog

All notable changes. Versions follow [Semantic Versioning](https://semver.org); `0.x` versions are pre-releases.

## [Unreleased]
- Fixed Apply having no effect on games where you had set custom artwork by hand in Steam: Steam shows that `.jpg` before our cover. Apply now moves it into the backup (Restore puts it back).

## [0.9.9] - 2026-10-08
- Tooltips wait a moment before showing, so a popup that takes the focus cannot flicker on and off.
- Downloads are only ever made over https, including after a redirect.
- Automatic checks on every change and weekly: tests on Windows, macOS and Linux, a security scan, a dependency check and a random-click robot that tries to break the window.
- Signed build provenance for release files, issue templates and this changelog.
- macOS: Apply tells the user to allow the permission prompt macOS shows the first time it closes Steam.
- README: the Terminal command is now the main macOS instruction; macOS is marked best effort.

## [0.9.8] - 2026-10-08
- Fixed the game list showing no games right after logging in: Steam lets the browser keep the logged-out page for an hour, so the button now opens a fresh address every time.
- Fixed macOS never detecting that Steam was running (so Apply never closed Steam and the dialog never warned). Steam is now found and closed on macOS.

## [0.9.7] - 2026-10-08
- The Download button opens Steam's login page first, then the game list.
- A game list saved while logged out gets a clear message, and a finished unusable file in Downloads is reported instead of ignored.
- The macOS app is ad-hoc signed, so macOS shows the normal "could not verify" prompt instead of calling it damaged.
- The save shortcut is shown as Cmd+S on macOS.

## [0.9.6] - 2026-10-08
- Progress counts only real games and skips apps Steam no longer lists, so a library of 1,338 items shows about 515.

## [0.9.5] - 2026-10-08
- Fixed "Could not reach Steam's servers" in the packaged Linux app (it looked for certificates in a folder that does not exist on SteamOS). The app now bundles trusted certificates.
- New `--check-network` option, and network errors now give the real reason.
- Themed confirmation and error dialogs with clear buttons; the desktop's own file chooser on Linux.

## [0.9.4] - 2026-10-08
- New: "Reset to Steam's default art" removes the covers this app made, with or without a backup.
- Restore walks back one step at a time; step 3 stays available when a backup exists.
- Relicensed to GPL-3.0-or-later.

## [0.9.3] - 2026-10-07
- First public pre-release: three-step window, command line, Windows, macOS and Linux builds, backups and undo, security hardening (earlier test builds 0.9.0 to 0.9.2 were withdrawn).
