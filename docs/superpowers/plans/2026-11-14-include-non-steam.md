# Include non-Steam games Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A switch, off by default, that gives a case to every non-Steam shortcut that already has a portrait in the account's `grid` folder.

**Architecture:** A new small module reads `shortcuts.vdf` and adds the shortcuts that have local art to the game list. The engine already builds a cover for any named game that has art (`custom_art`), so it is not changed. The command line and the Look screen set the switch, and the Make step passes it on. The switch is a saved setting like "Include software".

**Tech Stack:** Python 3.10+, PySide6 (QML), unittest. Run the Qt tests with `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests`.

**Spec:** `docs/superpowers/specs/2026-11-14-include-non-steam-design.md`

## Global Constraints

- Default off: with the switch off, nothing changes for anyone.
- Only shortcuts that already have a portrait in `grid` get a case. No fetching of art. Entries with no `appid` field are ignored.
- `shortcuts.vdf` is read through `engine/safefile.py` (size cap, no links followed blindly). A missing, huge, truncated or garbled file gives `{}`, never an error.
- Setting key `include_non_steam`, default `False`. Command line flag `--include-non-steam` on `make` and `run` only (not `list`).
- Switch label "Include non-Steam games", on the Look screen, "Art" section, after "Include software".
- With the switch on, art is searched even when "Use my own custom art" is off; the art of Steam games is kept only when that old switch is on; the art of shortcuts is always kept.
- Plain words in every user text. New window strings go into `qtui/i18n_pt_br.py` (Brazilian Portuguese, "você") and the help text into `tools/i18n_keys.py`.
- Conventional Commits. No `Co-Authored-By`, no Claude mention. Never push.

## Review Focus

- A shortcut whose id has no art stays out of the game list (Task 1).
- A shortcut id equal to a real Steam game's id never replaces that game's name (Task 1).
- A truncated or garbled `shortcuts.vdf` gives `{}` and no exception, including a name cut in the middle (Task 1).
- Switch on and "Use my own custom art" off: the shortcut gets its case, a Steam game that has its own art does not use it (Tasks 3 and 5).
- The Pick games flow does not list shortcuts and passes the switch as off (Task 5).

---

### Task 1: Reader and merge

**Files:**
- Create: `engine/shortcuts.py`
- Test: `tests/test_shortcuts.py` (new; follow the layout of a small existing test file, plain `unittest`, no Qt)

**Interfaces:**
- Produces: `read_shortcuts(steam: str, user: str | None = None) -> dict[int, str]` (unsigned app id to `AppName`; uses `steamcase.pick_account(steam, user)` for the folder; `{}` for anything unreadable); `add_non_steam(games: dict, found_art: dict, shortcuts: dict) -> dict` (for every shortcut id that has an entry in `found_art`: `games.setdefault(id, name)`, and return `{id: found_art[id]}` for exactly those; shortcuts without art are left out of both).

- [ ] **Step 1: Write the failing tests.** A helper `vdf(entries)` in the test builds a `shortcuts.vdf` in memory: `\x00shortcuts\x00`, then per entry `\x00<index>\x00`, `\x02appid\x00` + signed int32 little-endian, `\x01AppName\x00<name>\x00`, `\x01Exe\x00<exe>\x00`, `\x08` to close the entry, and a final `\x08\x08`. Tests (use a temp Steam folder with `userdata/111/config/shortcuts.vdf`; `read_shortcuts(steam, "111")`):
  - `test_reads_names_and_unsigned_ids`: appid `-296592220` and `1234567` give `{3998375076: "A", 1234567: "B"}`.
  - `test_entry_without_an_appid_is_ignored`.
  - `test_a_missing_file_a_garbled_file_and_an_empty_file_give_nothing`: no file, `b"not vdf"`, `b""`, `b"\x00" * 50` all give `{}`.
  - `test_a_truncated_file_never_raises`: cut the built file at every length from 0 to its size; each call returns a dict (it may hold the entries before the cut).
  - `test_a_file_over_the_cap_gives_nothing`: a file bigger than the module's `MAX_SHORTCUTS` constant (8 MB) gives `{}`.
  - `test_add_non_steam_adds_only_shortcuts_with_art`, `test_add_non_steam_never_renames_a_steam_game`, `test_add_non_steam_returns_only_the_art_of_what_it_added`.
- [ ] **Step 2: Run** `python3 -m unittest tests.test_shortcuts`. Expected: FAIL (`No module named 'engine.shortcuts'`).
- [ ] **Step 3: Implement** the module: `MAX_SHORTCUTS = 8 * 1024 * 1024`; a small tolerant binary VDF walker (types `\x00` map, `\x01` string, `\x02` int32, `\x08` end; keys compared case-insensitively because Steam has written both `AppName` and `appname`); catch `OSError`, `safefile` errors and every parse problem and return what was read so far or `{}`. Read with `safefile.read_small_file(path, MAX_SHORTCUTS, follow_links=True)` (the same choice `steamcase.read_text` makes for Steam files). One line on why the id is unsigned: Steam names the art `<unsigned id>p.png`.
- [ ] **Step 4: Run** `python3 -m unittest tests.test_shortcuts`. Expected: OK.
- [ ] **Step 5: Commit** `feat(engine): read non-Steam shortcuts`.

### Task 2: The engine builds a cover for a shortcut

**Files:**
- Test: `tests/test_steamcase.py` (class `NonSteam`, next to `Software`)
- Modify: `engine/steamcase.py` only if the test shows it must (expected: no change)

**Interfaces:**
- Consumes: nothing from Task 1; this task proves the engine path the spec relies on.

- [ ] **Step 1: Write the test** `test_a_shortcut_with_art_gets_a_cover_and_is_counted`: stub `store_items` to answer one real game (id 1, type 0) and nothing for id `3998375076`; stub `http_get` as in `Software.make`; save a small JPEG as the shortcut's art; call `sc.make_covers({1: None, 3998375076: "My Shortcut"}, out, custom_art={3998375076: art_path})`. Assert the file `My_Shortcut_3998375076.png` exists, `sc.cover_art(path)` is not `None`, and `r["ok"] == 2` (game 1 has no art in the stub, so it is counted as missing or ok depending on the stub: give it the same art stub as `Software.make` so it is `ok`), `r["unlisted"] == 0`.
- [ ] **Step 2: Run** `python3 -m unittest tests.test_steamcase.NonSteam`. Expected: PASS if the engine already handles it. If it FAILS, the failure shows which rule in `make_covers` rejects a nameless-in-store item; rule on the smallest engine change and ledger it.
- [ ] **Step 3: Commit** `test(engine): pin that a shortcut with art gets a cover`.

### Task 3: Command line

**Files:**
- Modify: `engine/steamcase.py` (`NON_STEAM_HELP` next to `SOFTWARE_HELP`; the `make` and `run` parser loop near the `--include-software` line; the custom-art block of `cmd_make`)
- Test: `tests/test_steamcase.py` (class `NonSteamCli(CustomArtCli)`, which already has `self.grid`, `self.mine(appid)`, `self.make(out, *extra)`)

**Interfaces:**
- Consumes: `shortcuts.read_shortcuts`, `shortcuts.add_non_steam` (Task 1).
- Produces: `NON_STEAM_HELP: str` (plain text, also used by the window in Task 4); flag `--include-non-steam` (`args.include_non_steam`).

- [ ] **Step 1: Write the failing tests** (write a `shortcuts.vdf` with the Task 1 helper next to `self.grid`, one shortcut id 4000000000 named "Cod Game", and `self.mine(4000000000)` for its art):
  - `test_flag_gives_a_shortcut_with_art_its_cover`: `make(out, "--include-non-steam")`; the file `Cod_Game_4000000000.png` exists and has art.
  - `test_without_the_flag_the_shortcut_is_ignored`: no such file.
  - `test_a_shortcut_without_art_is_ignored_with_the_flag`.
  - `test_the_flag_alone_does_not_use_the_art_of_steam_games`: `self.mine(1)` too; with only `--include-non-steam`, game 1's cover has no art (`sc.cover_art(...) is None`) while the shortcut's has.
- [ ] **Step 2: Run** `python3 -m unittest tests.test_steamcase.NonSteamCli`. Expected: FAIL (unrecognised argument).
- [ ] **Step 3: Implement** `NON_STEAM_HELP` ("Also make covers for the non-Steam games you added to Steam, when they already have a portrait in your Steam art folder. Games without one are left alone."); the `store_true` argument with that help; in `cmd_make`, after `_collect`: search art when `wanted_art or args.include_non_steam`; keep the existing Steam-art filtering exactly as now when `wanted_art`; when the flag is on, merge with `custom_art.update(shortcuts.add_non_steam(games, found, shortcuts.read_shortcuts(steam, args.user)))` (start from `{}` when only the flag asked for art). `cmd_run` goes through `cmd_make`.
- [ ] **Step 4: Run** `python3 -m unittest tests.test_steamcase`. Expected: OK (about 6 minutes).
- [ ] **Step 5: Commit** `feat(cli): add --include-non-steam`.

### Task 4: Saved setting and Look screen switch

**Files:**
- Modify: `qtui/settings.py` (`SETTING_KEYS`, `DEFAULTS`, the "six switches" wording becomes "seven"); `qtui/look.py` (one more `_art_switch` line, wording "three art switches" becomes "four"); `qtui/shell.py` (docstring count); `qtui/qml/LookScreen.qml`; `qtui/app.py` (context property `nonSteamHelp`); `qtui/i18n_pt_br.py`; `tools/i18n_keys.py`
- Test: `tests/test_qtui.py` (settings class; the Look screen switches test; the Look state test; the test that the switches go back to their defaults)

**Interfaces:**
- Consumes: `sc.NON_STEAM_HELP` (Task 3).
- Produces: setting `include_non_steam` (bool, default `False`, placed after `include_software`); `Look.includeNonSteam` (bool Property through `_art_switch`); QML object `look_include_non_steam` with tip `look_include_non_steam_tip`.

- [ ] **Step 1: Write the failing tests** by extending the existing ones where they already cover the sibling switches: the defaults assertion gets `"include_non_steam": False`; a settings file without the key loads it as `False`; the Look screen switch loop gets `"look_include_non_steam"` and its tip equals `NON_STEAM_HELP`; the remembered test sets and restores `includeNonSteam`; the defaults-after-Start-over test includes it.
- [ ] **Step 2: Run** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest tests.test_qtui.Settings tests.test_qtui.LookScreen tests.test_qtui.LookState`. Expected: the extended tests FAIL.
- [ ] **Step 3: Implement** the key, default, property, `SwitchRow` (`label: qsTr("Include non-Steam games")`, `tip: nonSteamHelp`), the context property, the `tools/i18n_keys.py` entry, and the Portuguese strings (label "Incluir jogos de fora da Steam"; help translated from `NON_STEAM_HELP`).
- [ ] **Step 4: Run** the same command plus `tests.test_i18n`. Expected: OK.
- [ ] **Step 5: Commit** `feat(qtui): add the Include non-Steam games switch to Look`.

### Task 5: Make step, Pick games, docs

**Files:**
- Modify: `qtui/make.py` (`start` early branch, `_art_worker`, `_make_worker`, the manual snapshot, the summary line); `qtui/i18n_pt_br.py`; `README.md`, `README.pt-BR.md`
- Test: `tests/test_qtui.py` (classes `MakeState`, `PickerTests`, `ManualMake`)

**Interfaces:**
- Consumes: `Look.includeNonSteam` (Task 4); `shortcuts.read_shortcuts`, `shortcuts.add_non_steam` (Task 1).
- Produces: snapshot key `snap["non_steam"]`; summary text "non-Steam games included" in the art value, after "software included".

- [ ] **Step 1: Write the failing tests**:
  - `MakeState`: with a stubbed `find_custom_art` (and a `shortcuts.vdf` in the fake Steam folder), switch on and own-art off: the games given to the stubbed `make_covers` include the shortcut and `custom_art` holds only the shortcut's art; switch off: the shortcut is absent.
  - The summary: art value ends with ", non-Steam games included" when on, and not when off (extend the existing choices test).
  - `PickerTests`: a shortcut with art and the switch on is not in `picker.rows`.
  - `ManualMake`: the engine's `games` do not include the shortcut with the switch on, and `snap["non_steam"]` is off in that flow.
- [ ] **Step 2: Run** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest tests.test_qtui.MakeState tests.test_qtui.PickerTests tests.test_qtui.ManualMake`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement**: snapshot `"non_steam": shell.switchValue("include_non_steam")`, forced `False` in the manual update (comment names it with the other Look switches); `start` searches art when `snap["custom"] or snap["non_steam"]`; in `_art_worker` keep Steam-game art only when `snap["custom"]`, then merge the shortcuts' art with `add_non_steam` before `games = set(games)`; in `_make_worker` call `add_non_steam(games, custom_art, read_shortcuts(steam, snap["account"]))` after `load_library` when the switch is on; the summary tuple gets `(tr("non-Steam games included"), look.includeNonSteam)` and its Portuguese string; both READMEs get a feature line and `--include-non-steam` in the options list (same places as `--include-software`).
- [ ] **Step 4: Run** the whole suite: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests`. Expected: OK (about 6 minutes). Also `python3 -m unittest tests.test_qtui` with the system Python. Expected: OK with skips.
- [ ] **Step 5: Commit** `feat(qtui): pass Include non-Steam games to the Make step`.
