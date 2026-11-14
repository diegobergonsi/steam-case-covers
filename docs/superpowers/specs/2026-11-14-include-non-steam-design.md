# Include non-Steam games in the covers (issue #73, problem 3)

## Why
A user reported that non-Steam shortcuts (for example Call of Duty: Modern Warfare 2, added to Steam by hand and given its own portrait) are completely ignored, so their library does not look uniform. The art is already on their disk, in the account's `grid` folder as `<id>p.png`. The engine already finds it (`find_custom_art` keys by app id and works for the large ids shortcuts use). What is missing is the shortcut itself: it is in neither the Steam library nor the installed games, so it never reaches the game list, and nothing gives it a name.

## Goal
A switch, off by default, that gives a case to every non-Steam shortcut that already has a portrait in the grid folder. Nothing changes for people who leave it off.

## Non-goals
- Fetching art for shortcuts that have none (SteamGridDB or anything else): it needs an API key and sends data to a third party. A shortcut without a local portrait is left alone.
- Shortcut entries that have no `appid` field (very old Steam versions). Steam computes their id; the first version ignores them rather than guess it. Upgrade if someone reports one.
- Listing shortcuts in the Pick games list (the list is built before Look, the same limit as "Include software").

## Approaches
1. **Switch "Include non-Steam games" on the Look screen, Art section, off by default** (chosen by the user). Matches "Include software" and "Use my own custom art". Nothing happens to art people placed by hand unless they opt in.
2. Automatic, no switch (not chosen): simpler, but it silently rewrites art people placed by hand.

## Design
- New module `engine/shortcuts.py` (steamcase.py is already about 2600 lines, so it does not grow): `read_shortcuts(steam, user=None) -> {appid: name}` reads `<steam>/userdata/<account>/config/shortcuts.vdf`. Binary VDF, read through `engine/safefile.py` with a size cap; a missing, huge, truncated or garbled file gives `{}`, never an error. The id is the entry's `appid` field read as an unsigned 32-bit number; the name is `AppName`.
- `steamcase.add_non_steam(games, art, shortcuts)`: for each shortcut whose id has an entry in `art`, put its name in `games` and keep its art. A shortcut with no art is not added. A real Steam game never gets its name replaced (`setdefault`).
- Art search: today the window only looks for art when "Use my own custom art" is on. With the new switch on it also looks, and keeps the art of Steam games only when the old switch is on; the art of shortcuts is always kept (it is their only source). Same rule in the command line.
- The store lookup is left as is: Steam answers an unknown large id with an empty item (checked 2026-11-14), and the engine already treats a game with a name and art as buildable.
- Setting `include_non_steam` (default False), `Look.includeNonSteam` through the shared `_art_switch` helper, a `SwitchRow` "Include non-Steam games" with a help tip, the Make summary says "non-Steam games included", the Pick games flow passes False. Command line: `--include-non-steam` on `make` and `run` (not on `list`: finding art copies files into the app's originals folder, and `list` stays read-only). New window strings go into `qtui/i18n_pt_br.py` and `tools/i18n_keys.py`; both READMEs list the switch.
- Apply, Reset and Restore are not touched: covers are named `<name>_<appid>.png` and copied to `<appid>p.png` like any other. The original art is kept by `find_custom_art` and comes back on Reset, like own art today.

## Known limits
- Pick games does not list shortcuts.
- Only shortcuts that already have a portrait get a case.
- Shortcut entries without an `appid` field are ignored.
- Not tried on Windows, macOS or a Deck; the path is the same relative path on every system.

## Left to the builder
The exact wording of the label, tip and summary text (plain words); the binary VDF parser internals.

## Checks
Tests first: the reader (a built file with two shortcuts, one with a signed negative id; an empty file; garbage; a truncated file; a huge file), `add_non_steam` (with art added, without art left out, a Steam game's name kept), the engine builds a cover for a shortcut and the result counts it, own-art off + non-Steam on keeps only the shortcut's art, the setting default and an old settings file, the Look switch, the Make step passing it, the command line flag on make, the Pick games flow passing False, Portuguese strings. Then the whole suite with Qt (`.venv`).
