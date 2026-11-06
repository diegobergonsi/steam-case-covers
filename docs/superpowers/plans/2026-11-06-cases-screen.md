# The Cases screen, clearer: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline, one task at a time, test first, commit per task). Steps use `- [ ]`.

**Goal:** the Case step has three sections, a preview, two-line group cards, a toast, a confirmed delete, and one filled button in the footer.

**Architecture:** `Cases` (Python) gains `previewSource`, `soFar`, a `subtitle` per group and a "left the saved group" notice; `Shell` gets a `toast(str)` signal; two new components, `GroupCard.qml` and `Toast.qml` (the toast lives in `Main.qml`); `CasesScreen.qml` is rebuilt on them. Text is in `qsTr` / Python `tr`, translated in `qtui/i18n_pt_br.py`.

**Tech stack:** Python 3, PySide6 / Qt Quick, unittest (`QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest`).

**Spec:** `docs/superpowers/specs/2026-11-06-cases-screen-design.md`

## Global constraints
- Conventional Commits, no attribution lines, never push. Branch `feat/cases-screen`.
- Test first. The suite stays green with and without Qt.
- Refinement, not redesign: tokens only from `Theme.qml`, no new colour or font, sky blue stays the one voice. Before the first QML edit, read `~/.claude/plugins/cache/impeccable/impeccable/4.7.0/skills/impeccable/reference/craft-floor.md`.
- Touch targets 44 px or more for new controls, nothing hover-only, 640 px width, 800 px height, keyboard and screen-reader names.
- **Lessons from PR #47:** (1) a test that changes text or the window size and then checks positions waits with `self.wait_for(...)` until the layout settles (Windows is slower than Linux; one test failed there); (2) never cut tests with a script: after editing `tests/test_qtui.py`, compare `git diff --stat` and the list of `def test_` lines added and removed; (3) before removing an object name, grep the whole repo (`qtui/__main__.py` selftest, docs, tools) for it.
- Public text never mentions Flatpak, Flathub or AUR. No screenshot of the real window or real Steam account is kept; render only with a fake HOME and fake Steam, then delete the images.

## Review Focus
1. A group with a 40-character name (the maximum) or a long case name: the card cuts line 1 and line 2 with "…", stays inside the window at 640 px, and the card keeps its height of at least 44 px.
2. Deleting the group that is chosen: the choice resets, the preview and the section heading follow, and cancelling the question changes nothing.
3. The toast appears only when a saved group was chosen and a case picture is clicked (not on the first pick, not when clicking the case already chosen), once per change, and goes away by itself.
4. Footer: a case chosen with no games ticked says "Next →" (never stuck); after assigning it says "Next →" again; with a saved group chosen it says "Add N games to <name>".
5. Language switch while on the screen updates headings, cards' second lines, "So far", the toast text of the next toast, and the delete question.

---

### Task 1: Cases model: preview address, "So far", subtitles, leaving a group

**Files:**
- Modify: `qtui/cases.py` (`pick`, `_pick_custom`, `groupList`, new properties); `qtui/shell.py` (signal `toast = Signal(str)`).
- Test: `tests/test_qtui.py` (a new class `CasesState(QtCase)` near `ShellHome`, built like `ShellHome.shell()`; reuse its helper to make a `Shell`).

**Interfaces:**
- Produces: `Shell.toast(str)` signal; `Cases.previewSource -> str` (property, notify `selectedKeyChanged` and `assignmentsChanged`): `image://preview/platform/<key>/<serial>` for the key chosen, else `previewKey`, else `steam` (the serial is the one `choices` uses, 1 except for the own case); `Cases.soFar -> str` (property, notify `assignmentsChanged`): "" when nothing is assigned, else `tr("So far: %s")` filled with `"label · N games"` entries joined by ", " (use `trn("%n game|%n games", n)`); each `groupList` entry gains `"subtitle"` = `"<case label> · <trn count>"`.
- Behaviour: when `pick(key)` or `_pick_custom()` changes the choice while `self._gid != ""`, emit `shell.toast` with `tr("You picked a new case, so the saved group was unselected.")` once. No toast when no saved group was chosen, or when the same case is clicked again with no group chosen.

- [ ] **Step 1: Failing tests** (`CasesState`): `test_preview_follows_the_choice_then_the_most_used_case_then_steam` (nothing -> `.../steam/1`; `pick("ps5")` -> `.../ps5/1`; after assigning a game to xbox360 and clearing the pick -> `.../xbox360/1`); `test_so_far_lists_the_cases_in_use` (empty string at first; after two assigns "So far: PlayStation 5 · 2 games, Xbox 360 · 1 game"); `test_a_group_has_a_subtitle_with_its_case_and_games` (saved group of the red Steam case with 3 games -> "Red Steam Case · 3 games" in the label the code produces; assert against `case_label`); `test_picking_a_case_while_a_saved_group_is_chosen_says_so_once` (connect `shell.toast`; `pickGroup(id)`; `pick("ps5")` -> one message; `pick("ps5")` again -> still one; with no saved group chosen, `pick` emits none).
- [ ] **Step 2: Run to fail:** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest tests.test_qtui.CasesState -v`. Expected: AttributeError / missing signal.
- [ ] **Step 3: Implement** the three members and the signal; keep `caption` and every other existing key of `groupList` (Home and Make use them).
- [ ] **Step 4: Run to pass**, then `tests.test_qtui.ManualWindow` (the Case tests are still the old ones and still green).
- [ ] **Step 5: Commit** `feat(qtui): the Cases model knows its preview, its so-far line and when a group is left`.

### Task 2: Two components: GroupCard and Toast

**Files:**
- Create: `qtui/qml/GroupCard.qml`, `qtui/qml/Toast.qml`; register both in `qtui/qml/qmldir`.
- Modify: `qtui/qml/Main.qml` (a `Toast` and a `Connections { target: shell; function onToast(text) { toast.show(text) } }`); `qtui/qml/Theme.qml` (`toastMs: 4000`, `groupCardWidth: 200`, any other size used); `docs/ui-guide.md` (components list, first: rule 5), `docs/DESIGN.md` (components).
- Test: `tests/test_qtui.py`, class `Components` (around 1520) for the two components in a small scene, and `ShellWindow` for the toast in the real window.

**Interfaces:**
- Produces: `GroupCard`: properties `string title, subtitle`, `bool chosen`, signal `picked()`; Accessible role RadioButton, `Accessible.checkable/checked`, name = title + ". " + subtitle; one Tab stop; Enter, Space and click pick it; border `Theme.accent` 2 px when chosen, `Theme.edge` 1 px otherwise, focus ring like `PathCard`; implicit height from the two lines, at least 44 px; both lines elide on one line; `enabled: false` greys it (`Theme.disabledOpacity`) and keeps it inert. `Toast`: `function show(text)`, `property int showMs: Theme.toastMs`, objectName `toast` and its text `toast_text`; hidden until shown; fades in and out over `Theme.dur(200)`; role `Accessible.AlertMessage` (it is `QAccessible.Role.AlertMessage` in PySide6; if QML has no such role, use `Accessible.StaticText` and say so in the ledger) with the text as the name; sits above the footer, centred in the screen area; a second `show` restarts the timer with the new text.

- [ ] **Step 1: Failing tests:** `GroupCard`: shows both lines; a long title and a long subtitle elide and stay inside a 200 px card; height at least 44; a click and Enter and Space emit `picked`; `chosen` changes the border colour (read `border.color`); role RadioButton, checked follows `chosen`. `Toast`: not visible at first; `shell.toast.emit("hello")` shows `toast_text == "hello"`; with `toast.setProperty("showMs", 50)` it is hidden again after `wait_for`; a second text replaces the first and restarts; with "Reduce effects" it appears at once (opacity 1 without waiting).
- [ ] **Step 2: Run to fail.**
- [ ] **Step 3: Implement** both components (a `Timer` for the toast; `Behavior on opacity` with `Theme.dur(200)`); add the guide and DESIGN.md entries.
- [ ] **Step 4: Run to pass**, `tests.test_qtui.Components` and `tests.test_qtui.Tokens` (the guide test lists components; the loose-number test forbids literals).
- [ ] **Step 5: Commit** `feat(qtui): a group card and a toast`.

### Task 3: The Cases screen rebuilt

**Files:**
- Modify: `qtui/qml/CasesScreen.qml` (rebuilt); the Case tests in `tests/test_qtui.py` class `ManualWindow` (about lines 7220 to 7330) and any other test that uses `case_assign`, `case_next`, `case_group_*`, `case_section_*`, `case_summary_*`, `case_applies`; `qtui/__main__.py` only if the selftest names a removed object (grep first).
- Test: the same class.

**Interfaces:**
- Consumes: Task 1 (`previewSource`, `soFar`, `groupList[].subtitle`, `shell.toast`) and Task 2 (`GroupCard`, `Toast`).
- Produces objectNames: sections `case_section_grid`, `case_section_group`, `case_section_options`; `case_preview` (the `PreviewCard`); `case_card_new` (the New group card) and `case_card_<groupId>` (saved groups); `case_no_groups` (the muted note, visible only with none saved); `case_group_name` and `case_colours` as before; `case_so_far`; `case_more` ("Pick more games"); `case_delete` (quiet "Delete this group", visible only when a saved group is chosen) and its dialog `case_delete_dlg` (a `ConfirmDialog` with `prefix: "case_delete_dlg"`, Cancel focused, confirm calls `cases.deleteGroup(selectedGroup)`); `case_main` (the single footer `PrimaryButton`); `case_error`, `case_own_hint`, `case_own_error`, `case_family`, `case_family_note` unchanged.

- [ ] **Step 1: Failing tests** (rewrite the old ones to the new names and add): sections are exactly three (`case_section_grid`, `case_section_group`, `case_section_options`); headings "Choose a case", "Add games to a group" (0 ticked) and "Add 3 games to a group" (3 ticked), "Options"; the preview source follows `cases.previewSource`; `case_main` is the only filled button of the window's Case screen (assert `filled` on it and not on `case_more`, `case_delete`); footer text: "Next →" with nothing chosen, "Use this case for 1 game" with a case chosen and 1 ticked, "Next →" with a case chosen and 0 ticked (and enabled once something is assigned), "Add 1 game to <group name>" with a saved group chosen; after `case_main` assigns, it reads "Next →" and `case_so_far` says "So far: PlayStation 5 · 1 game"; `case_card_new` second line is "Pick a case above" and then the case name; saved groups appear as `case_card_<id>` with title = name and subtitle = case · games; `case_no_groups` visible with none and hidden with some; choosing a saved card highlights its case picture (`case_<key>` chosen), hides `case_group_name`'s editing (read-only name shown) and the colours, shows `case_delete`; clicking a case picture while a saved group is chosen un-chooses it and shows the toast text; `case_delete` opens `case_delete_dlg` with the question text of the spec, Cancel changes nothing, confirm deletes and resets the choice; a 40-character group name keeps its card inside the window at 640 px (use `wait_for` after resizing); the old "long name keeps its delete button inside the window" test becomes the card version of the same check; the Steam case colours still appear only for the Steam case; a refused name still shows `case_error`.
- [ ] **Step 2: Run to fail:** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest tests.test_qtui.ManualWindow -v`.
- [ ] **Step 3: Rebuild `CasesScreen.qml`:** left column of sections inside `ScreenFrame` with `PreviewCard` beside them (the same side-by-side/above rule as `LookScreen.qml`, same `Theme.sectionMinWidth`); the case grid delegate stays as it is (move it unchanged into the first section); section 2 holds the card row (`Flow` of `GroupCard`), the muted note, the name field and colour swatches (as before, shown for a new group only), the error, the "So far" text and `case_more`, and `case_delete`; section 3 is the options section as before; a `Connections` is not needed here (the toast is in `Main.qml`). The footer is one `PrimaryButton` `case_main`: `text` = `canAssign ? (selectedGroup !== "" ? add-to-group text : use-this-case text) : qsTr("Next →")`, `enabled` = `canAssign || assignedCount > 0`, `onClicked` = `canAssign ? cases.assign() : shell.next()`.
- [ ] **Step 4: Run to pass**, then `tests.test_qtui.ManualWindow`, `HomeScreen` and `Tokens`; run the selftest (`.venv/bin/python -m qtui --selftest`).
- [ ] **Step 5: Commit** `feat(qtui): the Cases screen has three sections, a preview and one button`.

### Task 4: Portuguese, docs, changelog

**Files:**
- Modify: `qtui/i18n_pt_br.py`; `docs/ui-guide.md` (the Case step, rule 2); `docs/CHANGELOG.md` `[Unreleased]`; `README.md` and `README.pt-BR.md` only where they name the old buttons (grep "Use this case", "Your groups", "Delete group").
- Test: `tests/test_i18n.py` (it compares the table with `tools/i18n_keys.py`; remove keys no code uses any more).

- [ ] **Step 1: Failing test:** run `tests.test_i18n`; it lists the missing keys. Add one test that the new plural keys give "1 jogo" and "3 jogos".
- [ ] **Step 2: Add the entries** (feminine "case"): "Choose a case" -> "Escolha uma case"; "Add games to a group" -> "Adicionar jogos a um grupo"; "Add %n game to a group|Add %n games to a group" -> "Adicionar %n jogo a um grupo|Adicionar %n jogos a um grupo"; "New group" -> "Novo grupo"; "Pick a case above" -> "Escolha uma case acima"; "You don't have any groups yet." -> "Você ainda não tem grupos."; "So far: %s" -> "Até agora: %s"; "Delete this group" -> "Excluir este grupo"; "Delete the group “%s”?" -> "Excluir o grupo “%s”?"; "Its games lose this case here. Covers already on Steam stay until you Reset or make covers again." -> "Os jogos dele perdem esta case aqui. As capas que já estão na Steam ficam como estão até você Redefinir ou criar as capas de novo."; "Delete" -> "Excluir" (if not present); "You picked a new case, so the saved group was unselected." -> "Você escolheu uma nova case, então o grupo salvo foi desmarcado."; "%n game|%n games" already exists. Match the placeholder style the code uses (`%s` in Python, `%1` in QML).
- [ ] **Step 3: Docs and changelog** in plain words (the Case step has three sections and a preview; groups are two-line cards; one button at the bottom; a toast; deleting a group asks first).
- [ ] **Step 4: Run** the whole suite (`QT_QPA_PLATFORM=offscreen .venv/bin/python -W ignore -m unittest discover -s tests > <log> 2>&1`, read `Ran`/`OK`/`FAILED` from the log, about 4 minutes) and the selftest; all green.
- [ ] **Step 5: Commit** `feat(qtui): Portuguese and docs for the Cases screen`.

### Task 5: Look at it, polish, review, report

- [ ] **Step 1: Render** the Case screen (nothing chosen; a case chosen; a saved group chosen; no saved groups; the toast visible; the delete question) with a fake HOME and fake Steam at 640x552, 900x560 and 1280x800, in English and Portuguese. Use `QT_QPA_PLATFORM=offscreen` on a scratch copy of the QML whose `Card.qml` has the shadow effect removed (the real effect draws blank offscreen; xcb crashes in the Claude sandbox). Look at every image, fix what shows, delete the images.
- [ ] **Step 2: Run `/impeccable polish`** on `CasesScreen.qml`, `GroupCard.qml`, `Toast.qml`; fix every finding (a test first where a test can show it).
- [ ] **Step 3: Review with the thermo-nuclear standards.** `/thermo-nuclear-code-quality-review` is user-only; read `~/.claude/skills/thermo-nuclear-code-quality-review/SKILL.md` and dispatch a fresh reviewer on the most capable model with it, the review package, the spec, this plan, the Review Focus above and the ledger rulings. Fix every finding, minor ones too, in one pass, each with a test that failed first. Then run the whole suite again.
- [ ] **Step 4: Update** `claude-projects/steam-case-covers/` (`CONTEXT.md` current state and open items, `LOG.md`, `FEATURES.md`, `ARCHITECTURE.md` if components changed); commit there on `main`.
- [ ] **Step 5: Report** to the owner: what was fixed, what is open and why, what was not verified (Windows fonts, Deck touchscreen, macOS, a real screen reader), and that the branch is good to push. Do not push. After the owner pushes, open the PR with a simple description (plain words, a few emojis, no attribution line) when asked.

## Items 3 to 6 (not in this plan)
End of Apply with a result card and Undo in place; touch targets (settle 44 or 36 in the docs); contrast of faint text and control edge on raised fills; copy and joined sentences. Each gets its own spec and plan.
