# Manage a Group Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Manage button on each group of Home opens an overlay to add or remove games, rename and delete the group; the Home switches go and the Reset question gets a checklist of groups.

**Architecture:** One new QObject, `GroupManager` (`qtui/manage.py`), holds the open group and its ticks and does the saving. Remove, rename and delete go to `groups.json` and the cover notes at once (engine functions). Added games are staged in `Cases` like the Pick games path does (`Cases.stage`), so Make paints them later and nothing is saved for a game without a cover. The Reset question gains an optional checklist in `ConfirmDialog`.

**Tech Stack:** Python 3, PySide6 / Qt Quick (QML), unittest with `QT_QPA_PLATFORM=offscreen`.

**Spec:** `docs/superpowers/specs/2026-11-07-manage-groups-design.md` (mock: https://claude.ai/artifact/CKgsbZCqxEL7DqAmuSjteC)

## Global Constraints

- Run tests with `.venv/bin/python -m unittest ...` (the system Python has no PySide6, so every Qt test silently skips there).
- Conventional Commits; never a Co-Authored-By line; never `git push` (the user pushes).
- Durations only through `Theme.dur(90|120|200|260)`; no raw `duration:` numbers (`tests/test_tokens.py`).
- Touch targets at least `Theme.touchMin` (44); no hover-only behaviour.
- Every English string is the key in `qtui/i18n_pt_br.py`; README.md and README.pt-BR.md keep identical structure (`tests/test_i18n.py`, README tests).
- Section names are Title Case. A name has 1 to 40 letters, no control characters (`groups.MAX_NAME`).
- A game is in one group only; a group is never saved with no games; no cover is made inside Manage; nothing on Steam changes.
- Before any QML edit read `~/.claude/plugins/cache/impeccable/impeccable/4.7.0/skills/impeccable/reference/craft-floor.md` (mode: Operate).
- Tests wait for the window with `self.wait_for(...)`, never a bare `processEvents` after a model change.
- The notice sentence, exactly: `Changes show on your covers the next time you make covers, with “Same case” or “Pick games”. Nothing on Steam changes until then.` The toast after Save: `Saved. Your covers change the next time you make covers, with “Same case” or “Pick games”.`
- The warning, exactly: `No games ticked. Saving would delete this group.`

## Review Focus

1. A group game the store has no name for (delisted): its row must still show (name `Game <appid>`), ticked, so Save never silently removes it.
2. Manage opened while the library is still loading or failed to load: the list says so, and Save is disabled until the group's games can be listed.
3. Rename to its own name in other capitals is allowed; to another group's name (capitals ignored) is refused; spaces only or 41 letters is refused.
4. Save with nothing changed: closes, no toast, nothing written.
5. Ticking a game that is the last in another group: that group goes; and a staged add survives a later rename or removal done in Manage.

## File Structure

- `engine/groups.py`: add `rename`.
- `qtui/manage.py` (new): `GroupManager`.
- `qtui/cases.py`: add `stage`; `reloadGroups` keeps staged games.
- `qtui/picker.py`: add `Picker.games()` (the loaded `[(appid, name)]`) and a `tag` role on `RowsModel`.
- `qtui/shell.py`: create and expose `shell.manage`.
- `qtui/apply.py`: Reset question builds a checklist; ticks read at confirm.
- `qtui/qml/ManageGroup.qml` (new, registered in `qmldir`); `HomeScreen.qml`; `ConfirmDialog.qml`; `Main.qml`.
- `qtui/i18n_pt_br.py`, `README.md`, `README.pt-BR.md`, `docs/ui-guide.md`, `claude-projects/steam-case-covers/CONTEXT.md` and `LOG.md`.
- Tests: `tests/test_groups.py`, `tests/test_qtui.py` (new class `ManageGroups`, extends `WindowCase`), `tests/test_qtui_touch.py`.

---

### Task 1: Rename in the engine

**Files:** Modify `engine/groups.py`; Test `tests/test_groups.py` (class `Edit`).

**Interfaces:** Produces `rename(groups: list, group_id: str, name: str) -> list`. Returns a new list (the one given is not changed). `ValueError` with words for: invalid name (same text as `assign`), a name another group has (capitals ignored), unknown id.

- [ ] **Step 1: Failing tests** in `Edit`: `test_rename_changes_only_the_name`; `test_rename_to_the_same_name_in_other_capitals_is_allowed`; `test_rename_to_another_groups_name_is_refused` (also `"  red GAMES "` with spaces); `test_rename_refuses_empty_41_letters_and_line_breaks`; `test_rename_of_an_unknown_id_is_refused`; `test_rename_does_not_change_the_list_it_was_given`. Assertions use `assertEqual` on names and `assertRaises(ValueError)`.
- [ ] **Step 2:** Run `.venv/bin/python -m unittest tests.test_groups -v`; expect the six new tests to FAIL (`rename` missing).
- [ ] **Step 3:** Implement `rename` with `_name()`; copy each group dict.
- [ ] **Step 4:** Run the same command; expect all PASS.
- [ ] **Step 5:** `git commit -m "feat(engine): groups.rename"`

### Task 2: Stage added games in Cases

**Files:** Modify `qtui/cases.py` (near `assign`, `reloadGroups`); Test `tests/test_qtui.py` (class `ManageGroups`, create it here).

**Interfaces:** Produces `Cases.stage(group_id: str, appids: list[int]) -> None`: puts the games in the saved group as `assign` does (same case, `_assigned`, `_tones`, `_gids`, `_groups`, signals) without reading the picker and without unticking. Unknown id or empty list: no change. `Cases.reloadGroups()` keeps this run's staged games in their groups after re-reading the file.

- [ ] **Step 1: Failing tests** in `ManageGroups` (use `self.saved_groups()` as the Home tests do): `test_stage_puts_games_in_the_group_and_counts_them_as_given_a_case` (`cases.assignedCount` rises, `cases.groupList` count rises); `test_stage_moves_a_game_from_another_group_and_drops_that_group_when_empty`; `test_stage_of_an_unknown_group_changes_nothing`; `test_reloading_groups_keeps_the_staged_games` (stage, `reloadGroups()`, group still has them).
- [ ] **Step 2:** Run `.venv/bin/python -m unittest tests.test_qtui.ManageGroups -v`; expect FAIL.
- [ ] **Step 3:** Implement `stage` by sharing the body of `assign` (extract the part after the games and case are known into one private method both use). In `reloadGroups`, after loading, re-apply `_gids` entries with `groups.assign`.
- [ ] **Step 4:** Run the class and `tests.test_qtui.Cases*` (the existing Case step tests); expect PASS.
- [ ] **Step 5:** `git commit -m "feat(qtui): Cases.stage puts games in a saved group without the picker"`

### Task 3: GroupManager

**Files:** Create `qtui/manage.py`; Modify `qtui/picker.py` (`games()`, `tag` role), `qtui/shell.py` (`manage` property, constant); Test `ManageGroups`.

**Interfaces:** Consumes `groups.rename/drop_games/delete/save/load`, `sc.forget_group`, `Cases.stage`, `Picker.games()`, `Picker.ensureLoaded()`. Produces QML-visible `shell.manage`:
- `open(group_id: str)` slot; refuses (no change) while `shell.apply.busy` or `shell.make.running`.
- Properties: `isOpen: bool`, `groupId: str`, `title: str` (the group's saved name), `name: str` (the field, read/write), `model` (a `RowsModel`: appid, name, selected, tag), `query: str` (read/write, filters by name), `tickedCount: int`, `warning: str` (the exact warning, or ""), `error: str`, `loading: bool`, `canSave: bool` (library listed and not loading).
- Slots: `toggle(appid: int)`, `rename()` (saves the typed name to `groups.json` at once; sets `error` on `ValueError`), `save()`, `deleteGroup()` (asks nothing; the QML asks first), `cancel()`.
- Behaviour of `save()`: removed = saved games minus ticked; added = ticked minus saved. Nothing ticked: `sc.forget_group` for all its games, `groups.delete`, save. Otherwise: removed go through `groups.drop_games` + `sc.forget_group` + `groups.save`; added go to `Cases.stage`; `Cases.reloadGroups()` and `apply.groupTicks.refresh()` follow. Then `isOpen=False` and a toast (the exact toast sentence) unless nothing changed. An `OSError` on saving emits `shell.failed`-style message like `Make._save_groups` and keeps the window open.
- Rows show the group's games first-class: a game with no store name is `Game <appid>` and stays ticked (Review Focus 1). A game in another group has `tag` = that group's name.

- [ ] **Step 1: Failing tests** (names; assert on `shell.manage` and on `groups.load(self.covers)` and `sc.cover_group`): `test_open_ticks_the_groups_games`; `test_open_is_refused_while_apply_is_busy`; `test_a_game_without_a_store_name_stays_listed_and_ticked`; `test_unticking_a_game_removes_it_and_its_cover_loses_the_group_note` (cover fixture as in the Reset tests); `test_ticking_a_game_of_another_group_stages_it_and_tags_the_row`; `test_untick_all_shows_the_warning_and_save_deletes_the_group`; `test_save_with_no_change_writes_nothing_and_shows_no_toast`; `test_rename_saves_at_once_and_a_taken_name_sets_error`; `test_a_staged_add_survives_a_later_rename`; `test_cancel_drops_the_ticks`; `test_search_filters_rows_but_keeps_ticks`; `test_save_is_disabled_until_the_library_is_listed`.
- [ ] **Step 2:** Run the class; expect FAIL.
- [ ] **Step 3:** Implement `GroupManager` and the two `Picker` additions; `RowsModel` gets an optional `tag` (default `""`) so Pick games rows are unchanged.
- [ ] **Step 4:** Run the class and `tests.test_qtui.Picker*`; expect PASS.
- [ ] **Step 5:** `git commit -m "feat(qtui): GroupManager, the saving behind the Manage window"`

### Task 4: Home rows and the Manage overlay (QML)

**Files:** Create `qtui/qml/ManageGroup.qml`, register in `qtui/qml/qmldir`; Modify `qtui/qml/HomeScreen.qml` (groups Section), `qtui/qml/Main.qml` (hosts the overlay so it covers the window like `ConfirmDialog`); Test `ManageGroups`, `tests/test_qtui_touch.py`.

**Interfaces:** Consumes `shell.manage`. Object names: row `home_group_<id>` (Item with a `label` property: the group caption), button `home_manage_<id>`, overlay `manage_dialog`, `manage_name`, `manage_rename`, `manage_search`, `manage_list`, `manage_game_<appid>`, `manage_notice`, `manage_warning`, `manage_save`, `manage_cancel`, `manage_delete`, and the delete question `manage_delete_dialog` (a `ConfirmDialog`, Cancel focused: `Delete “%1”?`, `The group is removed. Covers already on Steam stay there. Your games are not touched.`, button `Delete group`).
- Overlay: dimmed window behind, card like `ConfirmDialog`, Escape cancels, Tab stays inside, focus returns to the Manage button. Rows at least 44 px. The group section's explanation line becomes: `Groups hold games that share a case. Manage changes which games are in a group, its name, or deletes it.` Manage buttons are `enabled: !screen.apply.busy && !shell.make.running`.

- [ ] **Step 1: Failing tests:** `test_home_lists_each_group_with_a_manage_button_and_no_switch`; `test_manage_opens_the_window_with_the_name_and_ticked_games`; `test_the_notice_is_always_shown_above_save`; `test_the_warning_shows_when_nothing_is_ticked`; `test_delete_asks_first_and_cancel_keeps_the_group`; `test_escape_closes_without_saving`; `test_manage_is_greyed_while_apply_is_busy`; touch: `test_manage_buttons_and_rows_are_44_tall`. Replace the old switch tests (`test_home_lists_the_groups_to_reset`, the label test) with these.
- [ ] **Step 2:** Run both test modules; expect the new tests FAIL.
- [ ] **Step 3:** Read `craft-floor.md`, then implement the overlay and the Home rows; reuse `QuietButton`, `PrimaryButton`, `ButtonRow`, `Section` styling, `Theme` tokens.
- [ ] **Step 4:** Run `tests.test_qtui tests.test_qtui_touch tests.test_tokens`; expect PASS.
- [ ] **Step 5:** `git commit -m "feat(qtui): a Manage button on each group opens a window to change it"`

### Task 5: Reset question with a checklist of groups

**Files:** Modify `qtui/qml/ConfirmDialog.qml`, `qtui/qml/Main.qml`, `qtui/apply.py` (`_scan_done` area, `_by_groups`, `_go`, `reset`); Test `ApplyState*` classes in `tests/test_qtui.py`.

**Interfaces:** `ConfirmDialog` gets `property var choices: []` (`{id, text, ticked}`), `signal choiceToggled(string id)`, objectNames `<prefix>_choice_<id>`; `ask(heading, texts, yes, alt, info, choices)` gains the optional sixth argument. Choice rows are in the Tab ring. `Apply` exposes `resetChoices` (`[{id, text, ticked}]`, only groups with covers on Steam) and slot `toggleResetGroup(group_id)`; ticks are read when the person confirms, and the covers to remove are recomputed then with `_by_groups`. With no group covers there is no checklist and the question is unchanged. When only group covers are left, the question still opens (the checklist is the way to reset them) instead of the old "Nothing to reset…Tick a group" toast.

- [ ] **Step 1: Failing tests:** `test_the_reset_question_lists_groups_with_covers_unticked`; `test_ticking_a_group_in_the_question_removes_its_covers_and_deletes_the_group` (extends the existing reset-with-groups tests: same end state as when the old switch was ticked); `test_an_unticked_group_stays_after_reset`; `test_reset_with_only_group_covers_still_asks`; `test_reset_without_groups_has_no_checklist`; `test_choices_are_reachable_with_tab_and_space`; `test_declining_the_question_ticks_nothing_for_the_next_one`.
- [ ] **Step 2:** Run `tests.test_qtui`; expect FAIL.
- [ ] **Step 3:** Implement as above; `GroupTicks` stays (Make still uses it), `Apply` stops reading ticks at `reset()`.
- [ ] **Step 4:** Run `tests.test_qtui tests.test_tokens`; expect PASS.
- [ ] **Step 5:** `git commit -m "feat(qtui): Reset asks which groups to reset too, in the question itself"`

### Task 6: Words, docs, and the whole suite

**Files:** Modify `qtui/i18n_pt_br.py`, `README.md`, `README.pt-BR.md`, `docs/ui-guide.md` (Home section and the section-controls rule), `docs/CHANGELOG.md` if the project lists unreleased changes there; `claude-projects/steam-case-covers/CONTEXT.md`, `LOG.md`.

- [ ] **Step 1:** `tests/test_i18n.py` already fails for every new English string; run it and add each missing key to `i18n_pt_br.py` (plain Portuguese, same tone).
- [ ] **Step 2:** README (both languages, same structure): where it describes groups, say Manage and that changes show on covers at the next make. Keep to the existing plain style. `tests/test_screenshots.py` must still pass.
- [ ] **Step 3:** Update `docs/ui-guide.md` (Home: Manage button, no switches; the new overlay; Reset question checklist).
- [ ] **Step 4:** Run the full suite: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests`; expect all PASS. Then once under load: `taskset -c 0` with three busy loops, expect PASS.
- [ ] **Step 5:** Update CONTEXT.md and LOG.md; `git commit -m "docs: Manage a group in the README, the UI guide and Portuguese"`. Note in CONTEXT.md: Home screenshots need retaking in a real desktop session.

## Self-Review

- Spec coverage: Manage button (T4), window parts (T3, T4), rename rules (T1, T3), tick/move/untick-all warning (T3, T4), notice and toast (T3, T4), Delete asks (T4), Reset checklist (T5), Make switches untouched (no task touches `MakeScreen.qml`), tests/docs/translations (T6).
- Names match across tasks: `GroupManager`, `shell.manage`, `Cases.stage`, `Picker.games`, `resetChoices`, `toggleResetGroup`, `choiceToggled`.
- Left to the builder: exact layout and spacing, which private helper `stage` shares with `assign`, the English wording of the Reset checklist labels.
