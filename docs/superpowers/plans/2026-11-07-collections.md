# Steam collections on "Pick your games" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On the Games screen, a row of Steam collection buttons; one click ticks all the games of that collection, with an Add / Replace / Cancel pop-up when games are already ticked.

**Architecture:** A pure reader in `engine/collections.py` turns Steam's `cloud-storage-namespace-1.json` into plain collections. `qtui/picker.py` keeps them next to the games, counts only games on screen, and does the ticking (add or replace). A new QML component `CollectionPills` draws the buttons and the "Show all" link; `GamesScreen.qml` wires it to the existing `ConfirmDialog` (confirm = Add, alternate = Replace, Cancel).

**Tech Stack:** Python 3, PySide6 / Qt Quick, `unittest` (Qt tests run offscreen).

**Spec:** `docs/superpowers/specs/2026-11-07-collections-design.md`

## Global Constraints

- Read-only, local only: the Steam file is never written, nothing goes over the network.
- Read it with `engine.safefile.read_small_file` (refuses links and non-regular files) with a cap of 8 MiB; any problem (missing, too big, bad JSON, odd shape) means no collections and no error shown.
- Collections shown: normal ones only (no `filterSpec`), not deleted, with a non-empty name, and at least one game that is in the list on screen. Favorites and Hidden are included. Members are `added` minus `removed`.
- Button order: most games first, then name (case-insensitive). Same-name collections stay separate buttons. Label is `Name (count)`.
- Pop-up rule: any ticked game, unless the click changes nothing (the selection already equals the collection's games on screen). Buttons: **Add them** (confirm, filled), **Replace them** (alternate), **Cancel** (focus, Escape).
- A collection click ignores the search box. "Ticked" is the whole selection, including games the search hides.
- Names come from the player: show them as plain text, never markup.
- Account: `shell.apply.accountChoice()` if set, else `sc.pick_account(steam)`; the reader takes the account as one argument. The file is re-read every time the Games screen opens.
- Look and rules of `docs/ui-guide.md`: pills 44 px high (`Theme.touchMin`), contrast WCAG AA on every fill, a section holds at most three controls (search, collections row, buttons row), messages are whole sentences with `%1` / `%n` blanks, English and Brazilian Portuguese.
- Conventional Commits, no Co-Authored-By line, never `git push`.

## Review Focus

1. A collection whose games are all outside the list on screen (or only some are): no button, or a count of the games on screen only. (Task 2)
2. Games ticked and then hidden by the search, then a collection click: the pop-up and its totals use the whole selection. (Task 2)
3. Steam's file is valid JSON but odd (a list of strings, `value` not JSON, ids that are not numbers, a link instead of a file, 20 MB): no crash, no row. (Task 1)
4. A collection named like markup (`<b>Done</b>`) or 200 characters long: drawn as plain text, the pill never wider than its row. (Task 3)
5. The game list changes (or the collection disappears from the file) while the pop-up is open: confirming must do nothing wrong and must not crash. (Tasks 2 and 3)

---

### Task 1: The collections reader

**Files:**
- Create: `engine/collections.py`
- Test: `tests/test_collections.py`

**Interfaces:**
- Produces: `MAX_FILE = 8 * 1024 * 1024`; `class Collection(NamedTuple)`: `id: str` (the file key, e.g. `user-collections.favorite`), `name: str`, `appids: frozenset[int]`; `read_collections(steam: str, account: str) -> list[Collection]`, in file order, `[]` on any problem, never raises.

- [ ] **Step 1: Write the failing tests** in `tests/test_collections.py` (plain `unittest`, files made in a temp folder at `<steam>/userdata/<account>/config/cloudstorage/cloud-storage-namespace-1.json`). Test names and assertions:
  - `test_plain_collections_are_read`: two entries, `favorite` (name "Favorites", added `[1, 2]`) and a custom one (name "100% Games", added `[3]`, removed `[3]` plus `[4]` added) give `Collection`s with names, `appids == frozenset({1, 2})` and `frozenset({4})` (removed is subtracted), ids equal to the keys.
  - `test_dynamic_deleted_and_nameless_are_skipped`: an entry with `filterSpec`, one with `"is_deleted": true`, one with name `""`, one with no name: result `[]`.
  - `test_ids_that_are_not_numbers_are_skipped`: `added: [1, "2", "x", None, 3.5]` keeps `{1, 2}`.
  - `test_odd_files_give_nothing_and_do_not_raise`: for each of a missing file, `"not json"`, `"{}"`, `'["a", 1]'`, `'[["user-collections.x", "text"]]'`, `'[["user-collections.x", {"value": "not json"}]]'`, `'[["user-collections.x", {"value": "[1]"}]]'`: `read_collections(...) == []`.
  - `test_a_link_and_a_huge_file_are_refused`: a symlink to a real valid file gives `[]` (skip on Windows with `os.symlink` unavailable); a file one byte over `MAX_FILE` gives `[]`.
  - `test_other_keys_are_ignored`: keys that do not start with `user-collections.` give `[]`.

- [ ] **Step 2: Run to verify it fails.** Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest tests.test_collections -v`. Expected: ImportError (no `engine.collections`).

- [ ] **Step 3: Implement** `read_collections` and `Collection` in `engine/collections.py` (licence header like the other engine files). The file is a JSON list of `[key, entry]` pairs; an entry's `value` is a JSON *text* holding `name`, `added`, `removed` and, for dynamic ones, `filterSpec`. Catch `OSError`, `ValueError`, `safefile` errors and shape errors; one bad entry is skipped, not the whole file. Do not reuse names from `engine/steamcase.py` (do not import it).

- [ ] **Step 4: Run to verify it passes.** Same command. Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add engine/collections.py tests/test_collections.py
git commit -m "feat(engine): read the collections Steam keeps for an account"
```

---

### Task 2: Collections in the Picker

**Files:**
- Modify: `qtui/picker.py`
- Test: `tests/test_qtui.py` (new class `CollectionTests(PickerBase)` after `PickerTests`)

**Interfaces:**
- Consumes: `engine.collections.read_collections(steam, account)`, `Collection` (Task 1); `sc.steam_dir()`, `sc.pick_account(steam, forced=None)`; `self._shell.apply.accountChoice()`.
- Produces on `Picker`:
  - `collectionsChanged = Signal()`
  - `collections` property (`QVariantList`, notify `collectionsChanged`): `[{"id": str, "name": str, "label": str, "count": int}]`, ordered and filtered as in Global Constraints; `count` is the collection's games that are in `self._all`.
  - `@Slot() refreshCollections()`: reads the file again (account as in Global Constraints; any `SteamcaseError`/`OSError` means no collections) and recomputes the list; emits only when the list changed.
  - `@Slot(str, result="QVariantMap") collectionPlan(collection_id)`: `{"name": str, "games": int, "ticked": int, "afterAdd": int, "ask": bool}`; `afterAdd` is the size of the selection after Add; `ask` is true when `ticked > 0` and the selection differs from the collection's games on screen. An unknown id gives `games: 0`, `ask: False`.
  - `@Slot(str, str) applyCollection(collection_id, mode)`: `mode` is `"add"` or `"replace"`; replace makes the selection exactly the collection's games on screen. Unknown id or mode: nothing happens. Always ends with the same refresh and `selectionChanged` as `toggle`.
  - `ensureLoaded()` also calls `refreshCollections()`; the collections are recomputed whenever `_all` changes (`_library_changed`, `_on_loaded`).

- [ ] **Step 1: Write the failing tests** in `CollectionTests(PickerBase)`. Write a helper that puts a collections file in `<self.tmp>/userdata/1234/config/cloudstorage/` (`PickerBase` already points `steam_dir` at `self.tmp`; names are `Hades`=1, `forza Horizon 5`=2, `God of War`=3). Tests:
  - `test_buttons_count_only_games_on_screen_sorted_and_labelled`: collections "Few" {1}, "Many" {1, 2, 99}, "Elsewhere" {98, 99}, "Apple" {3}: after `load()`, `labels == ["Many (2)", "Apple (1)", "Few (1)"]` (count desc, then name) and `Elsewhere` is absent.
  - `test_no_file_means_no_collections`: `collections == []`.
  - `test_installed_only_counts_installed_games`: with `self.library` limited to `{1: None}`, "Many" shows `(1)`.
  - `test_the_plan_asks_only_when_something_is_ticked_and_it_would_change`: nothing ticked: `ask False`; tick game 1: `ask True`, `ticked 1`, `afterAdd` right; selection equal to the collection: `ask False`.
  - `test_add_and_replace`: tick 3, then `applyCollection(many, "add")` gives `[1, 2, 3]`; `applyCollection(many, "replace")` gives `[1, 2]`; a bad mode and an unknown id change nothing.
  - `test_the_search_does_not_matter` (Review Focus 2): tick 1, search "forza", `collectionPlan` says `ticked 1`, `applyCollection(..., "replace")` leaves `selection() == [1, 2]` for a collection {1, 2}; `selectedCount` counts hidden games.
  - `test_a_new_game_list_drops_the_buttons_and_an_old_id_does_nothing` (Review Focus 5): after `load()`, change `self.shell.library.installedOnly` so the picker resets; `collections == []` and `applyCollection(old_id, "add")` leaves the selection empty.
  - `test_the_account_chosen_in_apply_is_used`: two account folders each with a different file; with `self.shell.apply.accountChoice` mocked to return the second, `refreshCollections()` shows that file's collections; without the mock the account `sc.pick_account` returns is used.
  - `test_a_collection_that_vanishes_from_the_file_after_a_refresh_is_gone`: rewrite the file, `refreshCollections()`, the button is gone and `collectionsChanged` was emitted once.

- [ ] **Step 2: Run to verify they fail.** Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest tests.test_qtui.CollectionTests -v`. Expected: FAIL (`collections` does not exist).

- [ ] **Step 3: Implement** the members above in `qtui/picker.py`. Keep the raw `Collection` list in one attribute and derive the shown list from it and `self._all`, so counts follow the game list without re-reading the file. `Picker` has no dependency on QML. Reading the file is synchronous (it is small and capped).

- [ ] **Step 4: Run to verify they pass.** Same command, then the whole `PickerTests` and `CasesTests` classes. Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add qtui/picker.py tests/test_qtui.py
git commit -m "feat(qtui): the Picker knows Steam collections and ticks a whole one, adding or replacing"
```

---

### Task 3: The buttons and the pop-up on the Games screen

**Files:**
- Create: `qtui/qml/CollectionPills.qml`
- Modify: `qtui/qml/qmldir` (register `CollectionPills 1.0 CollectionPills.qml`), `qtui/qml/GamesScreen.qml`, `qtui/i18n_pt_br.py`
- Test: `tests/test_qtui.py` (new class `CollectionsScreen(PickerBase)`), `tests/test_qtui_touch.py` (add the pills and the link to the tapped items it checks)

**Interfaces:**
- Consumes: `shell.picker.collections`, `collectionPlan`, `applyCollection`, `refreshCollections` (Task 2); `ConfirmDialog` (`ask(title, paragraphs, confirmText, alternateText)`, signals `confirmed`, `alternated`, `declined`).
- Produces: `CollectionPills` with `property var model` (list of `{id, label}`), `property string groupName`, `property bool expanded`, signal `picked(string id)`.

Behaviour of `CollectionPills` (a `Flow` of pills in the look of `ChoiceChips` but plain buttons: `Accessible.Button`, 44 px high, label drawn as plain text and elided so a pill is never wider than the row):
- Collapsed it shows two rows (`2 * Theme.touchMin + Theme.s8`, clipped). A pill that lies below those two rows is `enabled: false`, `activeFocusOnTab: false`, `Accessible.ignored: true` and invisible (`opacity: 0`) but stays in the layout.
- When the pills need more than two rows, a `QuietButton` below shows `qsTr("Show all %n collections", "", count)` (collapsed) or `qsTr("Show fewer")` (expanded). It does not exist (not visible) when everything fits.
- Object names: the component's own `objectName` is set by the screen; pills `<objectName>_pill_<id>`, the link `<objectName>_more`.

Wiring in `GamesScreen.qml`: in the "Find games" section after the buttons row, a muted `Text` "Your collections" (`games_collections_label`) and `CollectionPills { objectName: "games_collections" }`, both `visible` only when `picker.collections.length > 0`; `Component.onCompleted` also calls `picker.refreshCollections()` (via `ensureLoaded`). A click on a pill: `var p = picker.collectionPlan(id)`; if `p.games === 0` do nothing; if `!p.ask` call `applyCollection(id, "add")`; otherwise `dialog.ask(...)` with these whole sentences (English, with `%n` plurals and `%1`):
- title: "You already ticked %n game" / "…games" (plural of `ticked`)
- main paragraph: "“%1” has %n game on your list." (plural of `games`, `%1` the name)
- muted paragraph: "Add keeps your ticks and ticks the collection too: %n game in total." (plural of `afterAdd`) and a second muted paragraph "Replace unticks your games first: %n game in total." (plural of `games`)
- confirm text "Add them", alternate text "Replace them", cancel "Cancel". The `ConfirmDialog` has `objectName: "collections_dialog"`, `prefix: "collections_dlg"`, `focusBack` the pills row. `onConfirmed` calls `applyCollection(pendingId, "add")`, `onAlternated` calls it with `"replace"`; the id is remembered when the dialog opens.
Add every new English text to `qtui/i18n_pt_br.py` (Brazilian Portuguese, "você" register as the other texts); `tests/test_i18n.py` checks the table against `tools/i18n_keys.py`.

- [ ] **Step 1: Write the failing tests** in `CollectionsScreen(PickerBase)` (window on the Games step, using the file helper from Task 2; read the built window by object name with `self.item`). Tests:
  - `test_no_collections_no_row`: `games_collections` and `games_collections_label` are not visible.
  - `test_clicking_a_pill_ticks_its_games_without_a_question`: click `games_collections_pill_<id>`; `picker.selection()` is the collection's games and `collections_dlg_card` is not visible.
  - `test_with_ticks_the_dialog_asks_and_each_button_does_its_thing`: tick a game by hand, click a pill; dialog texts equal the sentences above with the numbers filled in; `collections_dlg_cancel` has the focus; Add gives hand-ticks plus collection; Replace gives the collection only; Cancel and Escape change nothing.
  - `test_a_long_or_markup_name_is_plain_and_fits` (Review Focus 4): a collection named `<b>Done</b>` shows that exact text with `textFormat` plain; one with 200 characters has a pill width at most the row width.
  - `test_more_than_two_rows_shows_the_link_and_hides_the_rest`: 25 collections: `games_collections_more` is visible and reads "Show all 25 collections"; a pill below the two rows has `activeFocusOnTab` false and `Accessible.ignored` true; after a click on the link every pill is focusable and the link reads "Show fewer"; with 3 collections the link is not visible.
  - `test_the_dialog_survives_a_game_list_that_changed` (Review Focus 5): open the dialog, switch `installedOnly` so the list resets, confirm Add: no exception, selection stays empty.
  - `test_the_new_texts_are_translated`: with `shell.setLanguage("pt-BR")` the dialog title and the link are not English.
  - In `tests/test_qtui_touch.py`: the pills and the link have a tap area of at least 44 x 44 (follow how the file checks the chips of other screens).

- [ ] **Step 2: Run to verify they fail.** Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest tests.test_qtui.CollectionsScreen tests.test_qtui_touch -v`. Expected: FAIL (items do not exist).

- [ ] **Step 3: Implement** `CollectionPills.qml`, the qmldir line, the `GamesScreen.qml` wiring and the Portuguese texts as described. Follow `ChoiceChips.qml` for colours, focus ring, hover and `Behavior`; use only `Theme` tokens (no new colours). The picker model exposes `label`, so the component needs no translation of the name.

- [ ] **Step 4: Run to verify they pass.** Same command, then `tests.test_i18n`, `tests.test_tokens`, and `.venv/bin/python -m qtui --selftest` (it must still pass). Look at the Games screen once in a real window (a fake HOME with a fake Steam and a collections file, as `tools/take_screenshots.py` does, never the real account) with 3 and with 25 collections, and the pop-up; read the sub-text contrast on the card fill (WCAG AA 4.5:1) from the built window, not by eye.

- [ ] **Step 5: Commit**
```bash
git add qtui/qml/CollectionPills.qml qtui/qml/qmldir qtui/qml/GamesScreen.qml qtui/i18n_pt_br.py tests/test_qtui.py tests/test_qtui_touch.py
git commit -m "feat(qtui): collection buttons on Pick your games, with an Add, Replace or Cancel question"
```

---

### Task 4: Docs, whole suite, review

**Files:**
- Modify: `README.md`, `README.pt-BR.md`, `docs/CHANGELOG.md` (`[Unreleased]`, "New"), `docs/ui-guide.md` (list `CollectionPills` among the components with its rule), `qtui/README.md` if it lists the QML components.

- [ ] **Step 1:** Add to both READMEs, where "Pick your games" is described, two plain sentences: one click on a Steam collection ticks its games; collections that Steam fills by a rule (dynamic ones) are not supported. Add a CHANGELOG line in the style of the other "New" items. Add the `CollectionPills` line to `docs/ui-guide.md`. No Flatpak, Flathub or AUR words, no real account names.
- [ ] **Step 2:** Run the whole suite: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests` (about 4 minutes). Expected: all pass, nothing new skipped.
- [ ] **Step 3:** Run `/thermo-nuclear-code-quality-review` on the branch and fix every finding, minor ones too, test first. Do not say the branch is good to push until this is clean.
- [ ] **Step 4: Commit**
```bash
git add README.md README.pt-BR.md docs/CHANGELOG.md docs/ui-guide.md
git commit -m "docs: Steam collections on Pick your games"
```
- [ ] **Step 5:** In `~/Projects/claude-projects/steam-case-covers/`, update `CONTEXT.md` ("Current state", "Open items"), `FEATURES.md` and `STEAM-FACTS.md` (the collections file and its format), and add a paragraph to `LOG.md`; commit there on `main`, never push.
