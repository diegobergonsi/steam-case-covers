# Include software in the covers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A switch, off by default, that makes covers for Steam software (type 6) as well as games.

**Architecture:** The engine learns one rule, "is this store item something that gets a cover", with a `software` argument. The command line and the Look screen set that argument, and the Make step passes it on. The switch is a saved setting like "Skip blurry covers".

**Tech Stack:** Python 3.10+, PySide6 (QML), unittest. Run the Qt tests with `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests`.

**Spec:** `docs/superpowers/specs/2026-11-14-include-software-design.md`

## Global Constraints

- Default off: with the switch off, nothing changes for anyone.
- Software is Steam type `6`. Tools (Proton, Steam Linux Runtime), demos, DLC and every other type stay skipped.
- Setting key `include_software`, default `False`. Command line flag `--include-software`.
- Switch label "Include software", on the Look screen, "Art" section, after "Skip blurry covers".
- Plain words in every user text. New window strings go into `qtui/i18n_pt_br.py` (Brazilian Portuguese, "você").
- Conventional Commits. No `Co-Authored-By`, no Claude mention. Never push.

## Review Focus

- A software item whose name matches `TOOL_NAMES` stays skipped with the switch on (test in Task 1).
- An item Steam no longer lists (type `None`, no name) with the switch on stays unlisted, not a cover (Task 1).
- A settings file saved by v1.7.0 (no `include_software` key) loads with the switch off (Task 3).
- The "Pick games" flow does not list software and does not crash with the switch on (Task 4).
- The results screen counts skipped items correctly with the switch on: software is made, not "skipped" (Task 4).

---

### Task 1: Engine rule

**Files:**
- Modify: `engine/steamcase.py` (constants near line 94; `list_games` ~706; `make_covers` ~1446, its two type checks ~1541 and ~1562)
- Test: `tests/test_steamcase.py` (new class `Software`, next to `Playtests`)

**Interfaces:**
- Produces: `SOFTWARE_TYPE = 6`; `is_coverable(item: dict, software: bool = False) -> bool` (True when `item.get("type", 0)` is in `GAME_TYPES`, or is `SOFTWARE_TYPE` and `software`); `list_games(games, log=None, errors=None, software=False)`; `make_covers(..., software=False)` (new keyword, after `skip_auto_art`).

- [ ] **Step 1: Write the failing tests** in class `Software(Base)`, modelled on `Playtests.test_a_playtest_gets_a_cover_like_a_game` (same stubbed `store_items` and `http_get`, items with `"type": 6`):
  - `test_software_is_skipped_by_default`: `list_games({1: None}) == []`; `make_covers` gives `r["ok"] == 0` and `r["not_games"] == 1`.
  - `test_software_gets_a_cover_with_the_switch`: `list_games({1: None}, software=True) == [(1, "G Software")]`; `make_covers(..., software=True)` gives `r["ok"] == 1`, `r["not_games"] == 0`.
  - `test_tools_and_other_types_stay_skipped_with_the_switch`: names `"Proton 9"` (type 6), and types `1` (demo) and `4` (DLC): all skipped with `software=True`.
  - `test_unlisted_item_stays_unlisted_with_the_switch`: `store_items` returns nothing for the id; `make_covers(..., software=True)` gives `r["unlisted"] == 1`, `r["ok"] == 0`.
- [ ] **Step 2: Run** `python3 -m unittest tests.test_steamcase.Software`. Expected: FAIL (`unexpected keyword argument 'software'`).
- [ ] **Step 3: Implement** `SOFTWARE_TYPE` and `is_coverable` beside `GAME_TYPES` (comment why 6: Lossless Scaling, Wallpaper Engine and Blender are type 6 and have normal art). Replace the three `it.get("type", 0) not in GAME_TYPES` checks with `not is_coverable(it, software)`; add the `software` parameter to `list_games` and `make_covers` and update both docstrings in one line each.
- [ ] **Step 4: Run** `python3 -m unittest tests.test_steamcase`. Expected: OK (about 3 minutes).
- [ ] **Step 5: Commit** `feat(engine): make covers for Steam software when asked`.

### Task 2: Command line flag

**Files:**
- Modify: `engine/steamcase.py` (`SOFTWARE_HELP` near `AUTO_ART_HELP` line 99; parser line ~2596; the `make_covers` call line ~2448)
- Test: `tests/test_steamcase.py` (class `Software`; find how an existing test drives the parser, for example the one that uses `--skip-auto-art`)

**Interfaces:**
- Consumes: `make_covers(..., software=...)` from Task 1.
- Produces: `SOFTWARE_HELP: str` (plain text, also used by the window in Task 3); flag `--include-software` (`args.include_software`).

- [ ] **Step 1: Write the failing test** `test_cli_flag_reaches_make_covers`: run the command line entry the way the neighbouring tests do, with `make_covers` stubbed to record its keywords; assert `software` is `True` with `--include-software` and `False` without it.
- [ ] **Step 2: Run** `python3 -m unittest tests.test_steamcase.Software`. Expected: FAIL (unrecognised argument).
- [ ] **Step 3: Implement** `SOFTWARE_HELP` ("Also make covers for software you own on Steam, such as Wallpaper Engine or Lossless Scaling. Steam's own tools, demos and DLC still get none."), the `store_true` argument with `help=SOFTWARE_HELP`, and pass `software=args.include_software`.
- [ ] **Step 4: Run** `python3 -m unittest tests.test_steamcase`. Expected: OK.
- [ ] **Step 5: Commit** `feat(cli): add --include-software`.

### Task 3: Saved setting and Look screen switch

**Files:**
- Modify: `qtui/settings.py` (`SETTING_KEYS`, `DEFAULTS`, lines 12-13); `qtui/look.py` (after `skipAutoArt`, ~line 261); `qtui/qml/LookScreen.qml` (after line 106); `qtui/app.py` (context property beside `autoArtHelp`, line 56); `qtui/i18n_pt_br.py`
- Test: `tests/test_qtui.py` (the settings test at ~line 491 and its neighbours; the Look test at ~1368; a QML-object test pattern as used for `look_skip_blurry`)

**Interfaces:**
- Consumes: `sc.SOFTWARE_HELP` (Task 2).
- Produces: setting `include_software` (bool, default `False`); `Look.includeSoftware` (bool Property, notify `artChanged`, saved through `shell.setSwitch("include_software", ...)`); QML object `look_include_software`.

- [ ] **Step 1: Write the failing tests**:
  - Update the `DEFAULTS` assertion (~line 491) to include `"include_software": False`.
  - `test_include_software_is_saved_and_restored`: set `look.includeSoftware = True`, build a new `Shell` on the same settings path, assert `switchValue("include_software")` and `Look.includeSoftware` are `True` (pattern of ~line 2586).
  - `test_old_settings_file_loads_with_software_off`: write a settings JSON without the key; the loaded value is `False`.
  - A test that the Look screen has an object named `look_include_software` whose `checked` follows `look.includeSoftware` (pattern of the existing `look_skip_blurry` test).
- [ ] **Step 2: Run** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest tests.test_qtui`. Expected: the new and updated tests FAIL.
- [ ] **Step 3: Implement** the key and default; `Look._get_software` / `_set_software` / `includeSoftware` copying the `skipAutoArt` trio; the `SwitchRow` (`objectName: "look_include_software"`, `label: qsTr("Include software")`, `tip: softwareHelp`); `ctx.setContextProperty("softwareHelp", i18n.tr(sc.SOFTWARE_HELP))`; the Portuguese strings for the label and the help text.
- [ ] **Step 4: Run** the same command. Expected: OK, including the existing test that checks every window string has a Portuguese entry.
- [ ] **Step 5: Commit** `feat(qtui): add the Include software switch to Look`.

### Task 4: Make step

**Files:**
- Modify: `qtui/make.py` (summary line ~200; snapshot ~255; `make_covers` call ~374)
- Test: `tests/test_qtui.py` (pattern of the test at ~6099 that checks the keywords given to `make_covers`; the summary-line test near `blurry art skipped`)

**Interfaces:**
- Consumes: `Look.includeSoftware` (Task 3); `make_covers(..., software=...)` (Task 1).
- Produces: snapshot key `snap["software"]`; summary text "software included" in the art value (after "blurry art skipped").

- [ ] **Step 1: Write the failing tests**:
  - `test_make_passes_include_software`: with `shell.setSwitch("include_software", True)` in the "same case" flow, the stubbed `make_covers` receives `software=True`; with it off, `False`.
  - `test_summary_mentions_software`: art line contains "software included" when on, and not when off (pattern of the "blurry art skipped" test).
  - `test_pick_games_flow_with_the_switch_on_still_makes_the_picked_games`: manual flow, switch on, the picked game is made and nothing raises.
- [ ] **Step 2: Run** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest tests.test_qtui`. Expected: the three new tests FAIL.
- [ ] **Step 3: Implement** `"software": shell.switchValue("include_software")` in the snapshot; `software=snap["software"]` in the call; `(tr("software included"), look.includeSoftware)` in the art tuple; its Portuguese string.
- [ ] **Step 4: Run** the whole suite: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests`. Expected: OK (about 7 minutes). Also run `python3 -m unittest tests.test_qtui` with the system Python (no PySide6) and expect OK with skips (a project gotcha).
- [ ] **Step 5: Commit** `feat(qtui): pass Include software to the Make step`.
