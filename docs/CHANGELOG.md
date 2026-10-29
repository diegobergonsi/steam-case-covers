# Changelog

All notable changes. Versions follow [Semantic Versioning](https://semver.org); `0.x` versions are pre-releases.

## [Unreleased]

## [1.5.0] - 2026-10-29
- New: a Halloween case theme. Under the colour swatches, "Case theme" offers "Classic" (as before) and "Halloween": a cobweb with a spider, a pumpkin and a spider hanging from the top, drawn on the case in whatever colour you picked. The Halloween case goes with the rosette-only marks for 100% games, so choosing it switches that choice to "Rosette only" and greys it out; going back to Classic restores your choice. Switching the theme asks before it replaces covers you already made, and "Remove only ours" still finds themed covers. On the command line: `--theme {classic,halloween}`; without it the covers already in the folder keep their theme. The artwork is original (see `docs/THIRD_PARTY.md`). Covers made before are untouched.
- New: a Discord icon at the top of the window, next to "Check for updates", opens the project's Discord invite in your browser when you click it (nothing is sent before that). If no browser opens, the link is copied and shown instead. The Discord mark is from Simple Icons (CC0) and only points to the project's server; see `docs/THIRD_PARTY.md`.
- New: the covers of your 100% games can have the rosette only, without the "100% Complete" ribbon over the art. In the window, a new choice above the case style picks "Rosette and ribbon" (as before, the default) or "Rosette only"; it works with every case style and is greyed out for "No special case". On the command line: `--completed-marks rosette`. The case style "Normal case with ribbon" is now called "Normal case", as the marks have their own choice. Covers made before are still found and kept.
- Fix: the command-line `apply` now refuses a covers folder that holds covers in more than one case colour (left behind when a colour change is interrupted) and tells you to run `make` again, instead of copying the mix into Steam. Nothing is changed and Steam is not closed.
- Documentation: the README header image now shows the front cover as a 100% game (gold case, rosette and ribbon).
- Documentation: the README links the project's Discord (feedback and bug reports are mainly handled there) and has a "Feedback and bugs" section; the issue template page offers it too. A "Support the project" section has a banner and a Ko-fi button, and the main README sections have one small emoji each. The repository page shows a "Sponsor" button that goes to the Ko-fi page.
- Documentation: the README shows two new Steam library screenshots (games at 100%, and a normal library with two 100% games) and has a shorter, grouped Features list.

## [1.4.0] - 2026-10-27
- Documentation files other than the README now live in the `docs/` folder.
- Step 2 has an optional block, "Highlight my 100% games". "Open my games page" opens your Steam games page; you save it from your own browser as "Webpage, Complete" (Chrome or Firefox), named `games.html`, and the app notices it in Downloads, or you pick it with "Browse…". Games with every achievement unlocked get a rosette at the top right, over the platform badges, and a "100% Complete" ribbon at the bottom. The choice can be picked once a page is loaded: "Gold case", "Gold border" (a gold border around the outside of the case, which gets about 5% smaller), "Normal case with ribbon" (the default) and "No special case". Only games already in your step 1 list can be highlighted. Switching the choice, or saving the page again after finishing another game and pressing Make covers, rebuilds only the covers that change. "No special case" removes the highlights on the next Make covers, after asking.
- The window says plainly that the saved page contains a temporary login token for your Steam account. The app only reads which games are at 100%: it never uses, stores or logs the token, and never deletes your files.
- `make` and `run` accept `--games-page FILE` and `--completed-style {ribbon,gold-case,gold-border,none}`. With a page and no style, it is `ribbon`; `none` removes the highlights. Without either option, covers keep their look.
- Covers record their treatment in a third PNG note (`steamcase-done`). Covers made before this change keep working, and "Reset to Steam's default art" ("Remove only ours") still finds the highlighted covers.
- Limits: the page lists about 99% of a library (509 of 515 covers on the author's), so a few old, free or hidden games cannot be highlighted. It shows progress only for games with at least one unlocked achievement, which is why only games at 100% are marked. Not tested: browsers other than Chrome, Steam in other languages, Windows, macOS and a real touchscreen.
- The case can now be any shade, from vivid to dark grey and black. Step 2 has three sliders (Colour, Colourfulness and Brightness) and nine swatches (the six colours, then Black, Graphite and Silver), with the live preview. Colourfulness and Brightness go from 0 to 100, where 100 is the original blue's level, and they only go down, so there is no white case. The white logo and text stay white, and the green family corner stays green on every case. The Replace prompt and the preview use all three values.
- `make` and `run` accept `--saturation PERCENT` and `--brightness PERCENT` (0 to 100) next to `--hue`. An option you leave out keeps the value of the covers already in the folder, else the original.
- Covers record their tone in a second PNG note (`steamcase-tone`). Covers made before this change keep working: they count as full colourfulness and full brightness, and Reset still finds them. One limit: a grey or black cover that another program re-saved and that dropped its PNG notes is not found by "Remove only ours". "Remove all" still removes it.
- Documentation: the README has a new screenshot of the window (with the colour row and the info badge), describes the colour choice and the family-games limit in "How it works", and has new FAQ answers for family games that got no cover and for changing the colour later.

## [1.3.1] - 2026-10-26
- An info badge (“i”) next to "Only my installed games" explains that games shared through Family Sharing, and games that are not installed, need your game list. The README says so too, and shows a new screenshot with the green family corner.

## [1.3.0] - 2026-10-26
- Choose the colour of the cases. Step 2 has a colour slider, six ready-made swatches and a live preview. Changing the colour asks before it replaces the covers you already made; covers made in another colour are rebuilt and the others are kept. Only the original blue is checked for readable text. The window remembers the colour of the covers you already made. A swipe that starts on the slider scrolls the page; only a tap or a sideways drag changes the colour. `make --hue DEGREES` does the same on the command line, and without `--hue` it keeps the colour of the covers already in the folder. The green family corner stays green in every colour, and Reset recognizes covers of any colour.
- Games from your Steam Family library (borrowed through Family Sharing) now get covers. They have a green corner with a family icon, so you can tell them from games you own. The app finds them in Steam's own files, so there is nothing extra to download. Free and bundled games you own are not marked. Only tested on a small family so far. Save your game list again after you buy games, so the new ones are not mistaken for family games.
- "Reset to Steam's default art" recognizes the new family covers as well as the old ones. `list` marks family games with `(family)`.

## [1.2.1] - 2026-10-21
- Windows: a cover could occasionally fail to save when antivirus or a second copy of the app held the file for a moment. Saving now waits and retries a few times.
- Windows: fixed a black window that flashed every few seconds and took the focus. The app checks whether Steam is running with `tasklist`, which opened a console window each time; it now runs hidden.
- Behind the scenes: an automatic Windows check now fails if the app ever opens a console window, and the release build uses newer GitHub artifact actions.

## [1.2.0] - 2026-10-20
- Touch works on handhelds: dragging the content scrolls the window (a drag never presses the button under your finger), the info badge and switches are bigger to tap, and a switch now changes when you lift your finger.
- The window follows how you resize it: text and button rows wrap, the header's "Check for updates" button moves under the title when narrow, and the window can be made much narrower and shorter than before.
- Buttons, switches, badges and the progress bar are drawn with smooth, perfectly round edges. Switches that are off now have enough contrast to see.
- "Check for updates" now says it opens this project's release page on GitHub (with the link) and that nothing is downloaded or installed unless you do it yourself there.

## [1.1.0] - 2026-10-12
- Layout follows the real text size, so the window is no longer clipped on screens with large text or 225% zoom.
- With two or more Steam accounts the window shows which account will be changed and has a "Change account" button. Apply, Restore and Reset use that choice.
- "Reset to Steam's default art" can also remove custom portraits that this app did not make (SteamGridDB, set by hand, `.jpg`, `.jpeg`, `.webp`). It asks first and keeps a backup; `reset --everything` does the same on the command line. Apply now also moves `.jpeg` and `.webp` art out of the way.
- Interface: a live Steam-is-open warning in step 3, a preview of finished covers, locked steps fold to one line, one main button at a time, better contrast, bigger click targets, clearer wording ("Download your game list", "Skip blurry covers"). Windows no longer waits on a process list when you click.

## [1.0.0] - 2026-10-08
First stable release. Windows is now tested on a real PC.
- If Apply fails and the old artwork cannot be put back, the backup is kept and the message says where it is, instead of the backup being deleted.
- Reviewed the new code (the `.jpg` move, the update check, network, process control and Reset) before this release.

## [0.9.11] - 2026-10-08
- A "Check for updates" button in the window and a `--version` option. It only asks GitHub when you click, tells you if a newer version exists and offers to open the download page; nothing is downloaded or installed. Release builds carry their version number.

## [0.9.10] - 2026-10-08
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
