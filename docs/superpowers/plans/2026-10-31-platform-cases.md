# Platform Cases and Manual Game Picking Implementation Plan

> **Later change (2026-11-01):** the final frames were hand-made, so `tools/build_cases.py` and its logo files are gone; `cases.json` is written from the frames by `tools/measure_cases.py` and has only `window` and `overlay` (no `marks_dy` or `corner`). On every case the rosette is at the left under the banner, the family corner at the top right, and the ribbon is 482 px wide. Read the sections below as the history of the design.


> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A second flow in the window where the user ticks specific games and puts them in console cases (PS3, PS4, PS5, Xbox 360, Xbox One, Xbox Series X|S, Switch, Switch 2, or the Steam case), ending in the same Make and Add to Steam as today.

**Architecture:** The engine (`steamcase.py`) learns a "platform" for a cover: its own frame and art window (`assets/cases/`), a PNG note `steamcase-platform` (the file is the single source of truth, like colour today), recognition for Reset/Restore, and `make_covers(platforms=...)`. Folder checks that compare colour/theme ignore platform covers. The window (`qtui/`) gets a `flow` ("natural" or "manual"), two new steps (Games, Case), a Home entry, and a manual path in `Make`.

**Tech Stack:** Python 3.10+, Pillow, PySide6/QML, unittest. Tests: `python3 -m unittest discover -s tests` and, with Qt, `QT_QPA_PLATFORM=offscreen <qtvenv>/bin/python -m unittest discover -s tests` (771 tests at the start; both must pass after every task).

**Spec:** `docs/superpowers/specs/2026-10-31-platform-cases-design.md`

## Global Constraints

- Test first for everything; Conventional Commits; NO attribution lines (no `Co-Authored-By`, no "Generated with"); never `git push`; work on `feat/platform-cases`.
- `assets/frame.png` is never regenerated; covers made before this feature must be recognised exactly as now.
- Cases: PS3, PS4, PS5, Xbox 360, Xbox One, Xbox Series X|S, Switch, Switch 2 (+ the Steam case). No colour, brightness, theme, gold case or gold border on platform covers. Every case is a 600x900 PNG (`SIZE`).
- Real console logos are wanted by the user (trademark risk accepted). Public text never mentions Flatpak, Flathub or AUR.
- The natural flow does not change; platform covers are left alone by it.
- Keep `docs/` and `CONTEXT.md` (in `claude-projects`) current as work happens. Tell the user plainly what was not run (Windows, macOS, the packaged build, real logos looked at on a real screen).

## Review Focus

1. A covers folder with platform covers beside Steam covers in a different colour or theme: `apply` (CLI), Make's "replace?" question, and the "mixed colour/theme" checks must not trip.
2. Natural-flow Make over a folder holding platform covers: they are kept as they are, counted as made, and still applied.
3. A forged or garbled note (`steamcase-platform = ps9`, a 600x900 PNG of the user's own with a valid note but other pixels): never recognised as ours, so Reset never removes it.
4. Offline or failing store lookup while the Games step loads names: a clear message, no crash, nothing ticked, Next stays disabled.
5. A 700-game list and a search with no match: the window stays responsive and says "No games match".

---

## File Structure

- Modify `steamcase.py`: platform constants and loaders next to the drawing section; `build_cover`, `preview_cover`, `is_steamcase_cover`, `make_covers`, and the folder checks of the apply section.
- Create `assets/cases/<platform>.png` (8 frames) and `assets/cases/cases.json` (per case: art window); built by new `tools/build_cases.py` from `tools/src/cases/*.svg`.
- Create `qtui/picker.py` (`Picker`: the Games step), `qtui/cases.py` (`Cases`: the Case step and the manual choices).
- Modify `qtui/steps.py`, `qtui/shell.py`, `qtui/make.py`, `qtui/reasons.py`, `qtui/qml/Main.qml`, `qtui/qml/HomeScreen.qml`, `qtui/qml/MakeScreen.qml`, `qtui/qml/HundredScreen.qml`; create `qtui/qml/GamesScreen.qml`, `qtui/qml/CasesScreen.qml`.
- Modify `steamcase-qt.spec` (ASSETS), `qtui/selfcheck.py`, `docs/THIRD_PARTY.md`, `README.md`, `docs/CHANGELOG.md` (under `[Unreleased]`).
- Tests: `tests/test_steamcase.py` (engine), `tests/test_qtui.py` (window).

---

### Task 1: Case registry, geometry and the frame builder (placeholder art)

**Files:** Modify `steamcase.py`; create `tools/build_cases.py`, `assets/cases/*.png`, `assets/cases/cases.json`; test in `tests/test_steamcase.py` (new class `PlatformCases`).

**Interfaces:**
- Produces in `steamcase.py`:
  - `PLATFORMS = ("ps3", "ps4", "ps5", "xbox360", "xboxone", "xboxseries", "switch", "switch2")`
  - `PLATFORM_LABELS: dict[str, str]` ("PlayStation 3", "PlayStation 4", "PlayStation 5", "Xbox 360", "Xbox One", "Xbox Series X|S", "Nintendo Switch", "Nintendo Switch 2")
  - `PLATFORM_CHUNK = "steamcase-platform"`, `CASES_DIR = os.path.join(HERE, "assets", "cases")`
  - `platform_window(platform: str) -> tuple[int, int, int, int]` (reads `cases.json`, cached; `ValueError` for an unknown platform)
  - `load_platform_frame(platform: str, family: bool = False) -> Image` (RGBA 600x900; with `family=True` the existing `FAMILY_CORNER` overlay is laid over it, clipped to the frame's alpha)
  - `_compose(art, frame, window=WINDOW)` (new optional argument; existing callers unchanged)

- [ ] **Step 1: Write the failing tests** in `PlatformCases`: `test_every_platform_has_a_frame_and_window` (for each of `PLATFORMS`: `load_platform_frame(p).size == SIZE`, mode RGBA, the window area is fully transparent, window inside the canvas, width and height each at least 400), `test_labels_cover_every_platform` (`set(PLATFORM_LABELS) == set(PLATFORMS)`), `test_unknown_platform_is_refused` (`ValueError` from `platform_window("ps9")` and `load_platform_frame("ps9")`), `test_family_corner_stays_inside_the_case` (with `family=True` no pixel is opaque where the plain frame is transparent), `test_compose_default_window_is_unchanged` (`_compose(art, frame)` equals the old result for the Steam frame, byte for byte).
- [ ] **Step 2: Run** `python3 -m unittest tests.test_steamcase.PlatformCases -v`. Expected: FAIL (names not defined).
- [ ] **Step 3: Implement** the constants and functions above in `steamcase.py` (drawing section). `tools/build_cases.py` draws, with Pillow, 8 PLACEHOLDER frames (rounded rectangle, a coloured banner with the platform label in the bundled Nunito Sans, a transparent art window) and writes `cases.json`. Placeholders are marked in the file header as such; Task 11 replaces them.
- [ ] **Step 4: Run** the new class, then both full suites. Expected: PASS, counts = 771 + new.
- [ ] **Step 5: Commit** `feat: registry and frames for console cases (placeholder art)`.

### Task 2: Building platform covers

**Files:** Modify `steamcase.py` (`build_cover`, `preview_cover`, new `cover_platform`); tests in `PlatformCases`.

**Interfaces:**
- Consumes: Task 1.
- Produces:
  - `build_cover(portrait_path, out_path, frame, hue=0, *, sat=100, val=100, treatment=None, theme=None, from_art=None, platform=None)`. With `platform`: `platform` must be in `PLATFORMS` (`ValueError`), `theme` must be None (`ValueError`), `treatment` must be None, `"ribbon"` or `"rosette"` (`ValueError`); the art is composed with `platform_window(platform)`; the PNG gets `PLATFORM_CHUNK` and, with a treatment, `DONE_CHUNK`; it gets NO hue, tone or theme note. The caller passes `frame=load_platform_frame(platform, family)`.
  - `cover_platform(path) -> str | None | False`: the note, read from the header only; None for a cover without it; False for an unreadable PNG or a note not in `PLATFORMS` (same contract as `cover_treatment`).
  - `preview_cover(..., platform=None)`: the default art in that case (same restrictions).

- [ ] **Step 1: Failing tests:** `test_build_writes_only_the_platform_note` (after `build_cover(..., platform="ps5")`: `cover_platform(out) == "ps5"`, `HUE_CHUNK`, `TONE_CHUNK`, `THEME_CHUNK` absent), `test_art_stays_inside_the_window` (a flat red portrait: the pixel just outside the window edge is not red, just inside is), `test_platform_with_theme_refused`, `test_platform_with_gold_treatment_refused` (`"gold-case"`, `"gold-border"`, `"gold-case-rosette"`), `test_marks_allowed` (`"ribbon"` and `"rosette"` build and `cover_treatment(out)` returns them), `test_cover_platform_garbled` (a PNG with note `ps9` -> False; no note -> None; a JPEG renamed .png -> False), `test_preview_cover_platform_size`.
- [ ] **Step 2: Run** `python3 -m unittest tests.test_steamcase.PlatformCases -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** Reuse `_tmp`/`_replace` exactly as `build_cover` does today.
- [ ] **Step 4: Run** both suites. Expected: PASS.
- [ ] **Step 5: Commit** `feat: build covers in console cases`.

### Task 3: Recognising platform covers (Reset and Restore)

**Files:** Modify `steamcase.py` (`is_steamcase_cover`, new `_platform_reference`); tests in `PlatformCases`.

**Interfaces:**
- Consumes: Tasks 1 and 2.
- Produces: `is_steamcase_cover(path)` also returns True for a platform cover; internally `_platform_reference(key: tuple, family: bool)` with `key = (platform, treatment)`, built like `_treated_reference` (the case made twice from flat black and flat white art; the mask is where both agree; the same "mask under 15% of the canvas means never ours" rule; lru_cache of 16).

- [ ] **Step 1: Failing tests:** `test_each_platform_cover_is_recognised` (all 8, with and without family corner, with `"ribbon"` and `"rosette"`; busy random art), `test_forged_note_with_other_pixels_is_not_ours` (a 600x900 PNG of noise with `steamcase-platform = ps5`), `test_wrong_platform_note_is_not_ours` (a ps5 cover re-saved with the note `ps4`), `test_garbled_note_is_not_ours`, `test_steam_covers_still_recognised` (existing fixtures untouched), `test_reset_removes_platform_covers` (extend the existing Reset setup: `find_our_covers` lists a ps5 cover beside a Steam one).
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement** the platform branch at the top of `is_steamcase_cover` (note present -> only the platform check decides).
- [ ] **Step 4: Run** both suites. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Reset and Restore recognise console covers`.

### Task 4: Folder checks ignore platform covers

**Files:** Modify `steamcase.py` (apply section); tests in `PlatformCases`.

**Interfaces:** Consumes `cover_platform`. Changes, all by skipping any cover where `cover_platform(path)` is not None: `covers_in_other_look`, `covers_with_other_art`, `covers_with_art`, `existing_cover_colour`, `mixed_cover_colours`, `covers_with_full_marks`, `covers_in_other_theme`, `mixed_cover_themes`.

- [ ] **Step 1: Failing tests** (one folder: one grey Steam cover and one ps5 cover): `test_mixed_colours_ignores_platform` (False), `test_mixed_themes_ignores_platform`, `test_existing_colour_skips_platform`, `test_covers_in_other_look_ignores_platform`, `test_apply_command_accepts_the_folder` (`cmd_apply` with a mocked Steam dir does not raise the "more than one colour" error), `test_full_marks_and_art_checks_ignore_platform`. Each also asserts the pre-existing behaviour with two Steam covers in different colours still returns True.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement** the skips.
- [ ] **Step 4: Run** both suites. Expected: PASS.
- [ ] **Step 5: Commit** `fix: console covers do not count as another colour or theme`.

### Task 5: `make_covers(platforms=...)`

**Files:** Modify `steamcase.py` (`make_covers`); tests in `PlatformCases` using `StoreMocks`.

**Interfaces:** `make_covers(..., platforms=None)`; `platforms: dict[int, str | None] | None`.
- `None` (natural flow): a game whose existing cover has a platform note is kept untouched: status "exists", counted in `ok`, listed in `files`, never rebuilt, not even with `force` (the only way to change a platform cover is a `platforms` dict).
- A dict (manual flow): only games in it are made (intersected with `only`); value `None` means the Steam case (made with `hue/sat/val/theme` as today), a platform name means that case (`treatment` must then be None, `"ribbon"` or `"rosette"` for all games, else `ValueError`; `theme` must be None if any game has a platform; `family` games get the corner). An existing cover is kept only if it already has the wanted platform (or none for `None`), the wanted treatment and the same art; otherwise it is rebuilt.
- Result gets `"platforms": int` (platform covers in `files`).

- [ ] **Step 1: Failing tests:** `test_manual_makes_only_listed_games_in_their_cases` (3 games, 2 listed: files exist for 2, `cover_platform` right, third not made), `test_steam_case_choice_rebuilds_a_platform_cover` (`{1: None}` over a ps5 cover gives a cover with no platform note), `test_platform_choice_rebuilds_a_steam_cover`, `test_same_choice_is_kept` (second run: all "exists", file mtimes unchanged), `test_natural_run_keeps_platform_covers` (including `force=True`), `test_natural_run_does_not_ask_about_them` (`covers_in_other_look` False), `test_unknown_platform_in_dict_refused`, `test_platform_with_gold_treatment_refused`, `test_family_corner_on_platform_cover` (the corner pixel is green only when the game is in `family`), `test_result_counts_platforms`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement** inside `make_covers`; frames cached per `(platform, family)` like `frame_for`; validate before any download (missing frame fails first, as now).
- [ ] **Step 4: Run** both suites. Expected: PASS.
- [ ] **Step 5: Commit** `feat: make covers in console cases`.

### Task 6: The Games step (Picker)

**Files:** Create `qtui/picker.py`, `qtui/qml/GamesScreen.qml`; tests in `tests/test_qtui.py` (class `PickerTests`, patching `steamcase.load_library` and `steamcase.list_games` as the existing tests patch the engine).

**Interfaces:**
- Produces `Picker(QObject)`: `loading` (bool), `status` / `statusKind`, `rows` (QVariantList of `{"appid": int, "name": str, "selected": bool}`, filtered by `query`, sorted by name case-insensitively), `query` (str, read/write), `selectedCount` (int, of ALL games, not only the filtered ones), Slots `load()` (worker thread: `sc.load_library(sc.steam_dir(), library path or None)` then `sc.list_games(games)`; signals back), `toggle(appid: int)`, `selectAllShown()`, `clearAll()`, and `selection() -> list[int]` (Python). Signals `rowsChanged`, `selectionChanged`, `failed(title, text)`.
- `Shell.picker` property and fact `picked` (True when `selectedCount > 0`).
- `GamesScreen.qml`: search field, count line ("N selected"), Select all shown / Clear, a `ListView` of rows with check boxes (keyboard: Space toggles), a "No games match" line when the filter is empty, footer button "Next: Case" (enabled when `selectedCount > 0`).

- [ ] **Step 1: Failing tests:** `test_load_lists_games_sorted_by_name`; `test_search_filters_case_insensitive_and_keeps_selection` (select "Hades", search "forza": count still 1, rows only Forza); `test_select_all_shown_only_affects_filtered`; `test_clear_all`; `test_no_match_status` ("No games match"); `test_load_failure_shows_message_and_ticks_nothing` (list_games raising `SteamcaseError`; `failed` emitted, `selectedCount == 0`, `loading` False); `test_empty_library_message`; `test_700_games_filter_is_fast` (700 rows, 20 queries under 1 s total); QML test: `GamesScreen` Next disabled with 0 selected, enabled with 1.
- [ ] **Step 2: Run** `QT_QPA_PLATFORM=offscreen <qtvenv>/bin/python -m unittest tests.test_qtui.PickerTests -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** Follow the threading pattern of `qtui/make.py` (worker + private signals tagged with a request number; ignore stale answers; survive a closing window).
- [ ] **Step 4: Run** both suites. Expected: PASS.
- [ ] **Step 5: Commit** `feat: the Games step`.

### Task 7: The Case step (Cases)

**Files:** Create `qtui/cases.py`, `qtui/qml/CasesScreen.qml`; extend `qtui/preview.py`'s image provider with platform previews; tests in `tests/test_qtui.py` (`CasesTests`).

**Interfaces:**
- Produces `Cases(QObject)`: `choices` (QVariantList of `{"key": "steam"|<platform>, "label": str}` in this order: steam, ps5, ps4, ps3, xboxseries, xboxone, xbox360, switch2, switch), `selectedKey` (str; `""` until a case is clicked, so nothing is pre-selected), Slot `pick(key: str)`, Slot `assign()` (puts the Picker's selection into `assignments` with the picked case, clears the Picker's selection, emits `assignmentsChanged`; does nothing without a picked case or an empty selection), `assignments` (dict appid -> platform or None, Python via `assigned()`), `assignedCount` (int), `summary` (QVariantList of `{"label", "count"}` per case used), switches `family` (bool, default False) and `highlight` (bool, default False) and `marks` ("full" | "rosette", default "full") with their notify signals; `treatment() -> str | None` (`None` unless `highlight`; else `sc.compose_treatment("ribbon", marks)`); `Slot reset()`.
- Fact `assigned` on the Shell (`assignedCount > 0`).
- Preview images: `image://preview/platform/<key>` returns `sc.preview_cover(platform=key)` (for `steam`: the current default preview); the grid shows the real overlay of each case, 3 columns.
- `CasesScreen.qml`: the grid, a line "Applies to N selected games", button "Use this case for N games" (primary), a summary list ("PlayStation 5: 3 games"), the two switches ("Mark family games" with the same help tip as the Look screen and disabled with the same reason when installed-only is on or no list is loaded; "Highlight my 100% games" with a Choice "Rosette and ribbon" / "Rosette only"), footer "Next" (enabled when `assignedCount > 0`), and a quiet "Pick more games" button that goes back to the Games step. Picking more is never required.

- [ ] **Step 1: Failing tests:** `test_pick_then_assign_moves_selection_to_assignments`; `test_assign_without_a_case_does_nothing`; `test_assign_twice_overwrites_a_games_case` (game 1 to ps5, later to xbox360: only xbox360 remains; `assignedCount` still 1); `test_steam_choice_is_none`; `test_treatment_only_when_highlight_on`; `test_family_disabled_when_installed_only` (reason text equals the Look screen's); `test_choices_order_and_labels`; `test_preview_url_returns_600x900`; QML: the "Use this case" button is disabled until a case is picked and games are selected.
- [ ] **Step 2: Run** `... tests.test_qtui.CasesTests -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** both suites. Expected: PASS.
- [ ] **Step 5: Commit** `feat: the Case step`.

### Task 8: The two flows (steps, shell, Home, navigation)

**Files:** Modify `qtui/steps.py`, `qtui/shell.py`, `qtui/qml/Main.qml`, `qtui/qml/HomeScreen.qml`; tests in `tests/test_qtui.py` (`FlowTests`; the existing `step_states` tests stay unchanged).

**Interfaces:**
- `steps.py` produces: `STEPS_MANUAL = ("home", "game_list", "pick", "case", "hundred", "make", "add")`; `labels(flow) -> dict` (manual: "1  Game list", "2  Games", "3  Case", "4  100% games", "5  Make", "6  Add to Steam"; natural unchanged); `manual_step_states(ready, picked, assigned, hundred_done, covers_made, applied) -> dict` (same chain rule as `step_states`: a step is done only if its fact is true and the step before is done; `picked` and `assigned` both required for "case" to be done).
- `Shell`: `flow` property ("natural" default; notify `flowChanged`), Slots `startManual()` and `startNatural()` (rebuild the steps, reset `current` to the first step that is not done, keep facts; `look_done` is irrelevant in manual), `FACTS` gains `picked`, `assigned`; the nav model, `resume`, `returning` use the current flow. Switching flow while Make or Apply is running is ignored.
- `HomeScreen.qml`: under "Start →" a second quiet button "Pick games by hand" (`objectName: "home_manual"`) with one line under it: "Choose games and put them in PlayStation, Xbox or Nintendo cases." In the Dashboard state both entries stay.
- `Main.qml`: the Loader maps `pick` -> `GamesScreen.qml`, `case` -> `CasesScreen.qml`; frozen earlier steps also cover `pick` and `case` while Make runs.

- [ ] **Step 1: Failing tests:** `test_manual_states_chain` (nothing ready: game_list active, rest locked; ready+picked+assigned: case done, hundred active), `test_assigned_without_picked_does_not_unlock`, `test_startManual_changes_nav_labels_and_keys`, `test_startNatural_restores_the_five_steps`, `test_flow_switch_ignored_while_making`, `test_shared_game_list_serves_both_flows` (load a list in natural, switch to manual: `ready` still True), QML: Home shows `home_manual`, clicking it makes `shell.flow == "manual"` and the nav has 7 rows.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** both suites. Expected: PASS.
- [ ] **Step 5: Commit** `feat: a manual flow reachable from Home`.

### Task 9: Making covers in the manual flow

**Files:** Modify `qtui/make.py`, `qtui/reasons.py`, `qtui/qml/MakeScreen.qml`, `qtui/qml/HundredScreen.qml`; tests in `tests/test_qtui.py` (`ManualMakeTests`, using the `StoreMocks`-style fake store of `test_qtui.py`).

**Interfaces:**
- `Make.start()` branches on `shell.flow`. Manual snapshot: `platforms = shell.cases.assigned()`, `treatment = shell.cases.treatment()`, `completed` from `hundred.values()[0]` only when `treatment` is not None (else None), `family` only if `shell.cases.family` is on, `theme=None`, tone from the Look object (used by games set to the Steam case). The worker calls `sc.make_covers(games, covers, platforms=platforms, family=..., completed=..., treatment=..., hue/sat/val=..., custom_art={}...)`; `Make.files()` returns only this run's covers, so Apply adds only the ticked games.
- `reasons.platform_replace_reason(covers_dir, platforms, treatment) -> tuple[str, str] | None`: a question (title, sentence) when an existing cover of a listed game would be rebuilt because its case or marks change; None otherwise. The sentence names the number of covers.
- `result_text` gains: " N of them are in a console case." when `res["platforms"]`.
- `MakeScreen.qml`: in the manual flow the "What you chose" summary shows Games ("N games"), Cases (e.g. "PlayStation 5, Xbox One"), 100% games, and each row's change link goes to the matching manual step; no Colour/Theme/Art rows.
- `HundredScreen.qml`: in the manual flow the gold choices are hidden; only on/off and the marks choice remain (a style other than "No special case" means highlight on).

- [ ] **Step 1: Failing tests:** `test_manual_make_calls_engine_with_platforms` (engine patched on `steamcase`; assert `platforms`, `treatment` and `only` semantics), `test_manual_make_applies_only_ticked_games` (`make.files()` has 2 files for 2 games out of 3 in the library), `test_question_when_a_case_changes` and `test_no_question_for_new_games` (`platform_replace_reason`), `test_natural_make_unchanged` (the existing Make tests pass untouched), `test_result_text_mentions_console_cases`, `test_manual_summary_rows`, `test_gold_choices_hidden_in_manual_flow`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** The question reuses the existing confirm flow of `Make` (`confirmNeeded`).
- [ ] **Step 4: Run** both suites. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Make works in the manual flow`.

### Task 10: End-to-end check of the manual flow (engine and window together)

**Files:** tests only (`tests/test_qtui.py`, class `ManualFlowEndToEnd`).

- [ ] **Step 1: Write the test** `test_pick_case_make_apply_restore`: fake Steam folder with a grid, fake store and download; load a list of 3 games; `startManual`; tick 2 (`toggle`), `pick("ps5")`, `assign()`; Make; assert two `ps5` covers exist and the third game has no cover; Apply with Steam not running; assert the two files are in the grid and nothing else changed; Restore; assert the grid is as before. Then `test_reset_removes_console_covers` (Reset finds them). Then a second round (`pick("xbox360")` for another game) before Make gives a mixed folder: assert `cmd_apply`'s checks do not raise.
- [ ] **Step 2: Run** and fix whatever it exposes, test first for each fix.
- [ ] **Step 3: Run** both suites. Expected: PASS.
- [ ] **Step 4: Commit** `test: the manual flow from picking to restore`.

### Task 11: Real artwork, logos and packaging (needs the user's eyes)

**Files:** Replace `assets/cases/*.png`, `cases.json`, `tools/build_cases.py`, `tools/src/cases/*.svg`; modify `steamcase-qt.spec`, `qtui/selfcheck.py`, `docs/THIRD_PARTY.md`.

- [ ] **Step 1: Failing tests:** `test_spec_lists_the_case_assets` (every file in `assets/cases/` appears in `steamcase-qt.spec`, destination `assets/cases`), `test_selfcheck_builds_a_console_cover` (`qtui.selfcheck.engine_problems()` also builds and recognises one ps5 cover), `test_third_party_names_the_logos` (the file mentions each logo source and the trademark notice).
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Draw the 8 real cases** as SVG sources (case shape, banner, spine-less front, the platform's colours) with the real logo files; record each logo's source and licence in `docs/THIRD_PARTY.md` with: "PlayStation, Xbox and Nintendo marks belong to their owners; this project is not affiliated with them." If a logo's vector source or licence cannot be found, STOP and tell the user (do not draw a lookalike).
- [ ] **Step 4: Look at every case** with `preview_cover(platform=p)`, with and without family corner, `"ribbon"` and `"rosette"`: the corner and marks must not hide the logo. Save the 8x4 contact sheet in the session scratchpad and show it to the user; if a mark clashes with a logo, report it and ask. Not shown on a real screen yet means "not verified" in the report.
- [ ] **Step 5: Run** both suites. Expected: PASS.
- [ ] **Step 6: Commit** `feat: console case artwork`.

### Task 12: Docs and wrap-up

**Files:** `README.md`, `docs/CHANGELOG.md` (`[Unreleased]`), `docs/PRODUCT.md` if it lists features, `claude-projects/steam-case-covers/CONTEXT.md`.

- [ ] **Step 1:** Add the manual flow to the README (what it is, the 8 cases, the options, that games never picked keep the Steam case) and one line in the changelog under `[Unreleased]`.
- [ ] **Step 2:** Update `CONTEXT.md` (file map, engine functions, session log with what was and was not run).
- [ ] **Step 3: Run** both suites, `python steamcase.py -h`, `QT_QPA_PLATFORM=offscreen <qtvenv>/bin/python -m qtui --selftest`. Report the counts and anything not run (Windows, macOS, packaged build, real logos on a real screen, gamepad/touch).
- [ ] **Step 4: Commit** `docs: the manual flow and console cases`.
- [ ] **Step 5:** Ask the user before any push, PR or workflow run (the PR text follows the user's rule: short, pretty, plain words).
