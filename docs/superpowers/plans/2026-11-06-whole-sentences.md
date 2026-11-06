# Whole sentences for translation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Five messages that are built from translated pieces become one message each, with a blank for the changing part; the texts people see do not change.

**Architecture:** In QML a blank is `%1` filled with `.arg(...)`; in Python it is `%s`, as the rest of the app does (`PAGE_HELP_TEMPLATE % SAVE_KEY`). Two guard tests (no `qsTr(...)` glued to something; no Portuguese message that is a fragment) fail first. Then the five places and the Portuguese list change together.

**Tech Stack:** QML, Python (`qtui/cases.py`, `qtui/i18n_pt_br.py`), `unittest` (`tests/test_i18n.py`, `tests/test_qtui.py`).

**Spec:** `docs/superpowers/specs/2026-11-06-whole-sentences-design.md`

## Global Constraints
- English and Portuguese texts as people see them stay exactly as today, including the screen reader names.
- Every message has a Portuguese entry (`tests.test_i18n` checks it both ways: nothing missing, nothing left over).
- The key name on the Step 1 instruction is `saveKey` (Cmd+S on macOS, Ctrl+S elsewhere), still from the computer.
- Only the five places in the spec change. Joins of whole sentences, `" · "` and `". "` separators, and the comma in `reasons.py` stay.
- Commits: Conventional Commits, no Claude co-author line, never push.

## Review Focus
- The macOS key: the Step 1 instruction must show `Cmd+S` when the app's `saveKey` is `Cmd+S` (Task 2 test sets it).
- A menu step with no hint and one with a hint ("(optional)") both read right in the screen reader name, locked and done.
- "Steam case, custom colour" still reads right when the colour is not one of the app's own.
- A percent sign or `%` next to a blank must not break formatting: `"Steam case, %s"` is the only new Python template and has no other `%`.
- The Portuguese of each changed message equals today's text put together (Task 2 pins each).

---

### Task 1: Two guard tests that fail today

**Files:**
- Test: `tests/test_i18n.py` (new class `WholeSentences`)

**Interfaces:**
- Consumes: the Portuguese table of `qtui.i18n_pt_br` (as `Words` in the same file reads it), `QML_DIR`-style path `qtui/qml`.
- Produces: nothing later tasks call.

- [ ] **Step 1: Write the failing tests.**
  - `test_no_qml_text_is_glued_to_a_translated_piece`: for every `.qml` file in `qtui/qml`, no match of `qsTr\([^)]*\)\s*\+` or `\+\s*qsTr\(`; the failure message names the file.
  - `test_no_portuguese_message_is_a_fragment`: no key of the Portuguese table starts with one of `, . : ; )` or ends with one of `, : (` (ignoring one trailing space); the failure lists the first 60 characters of each.
- [ ] **Step 2: Run them.** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest tests.test_i18n.WholeSentences`. Expected: both FAIL. The first names `GameListScreen.qml`, `NavItem.qml` and `ChoiceSummary.qml`; the second lists `. Change`, `, locked`, `, done` and `Steam case, `.
- [ ] **Step 3: Commit** `test(i18n): no text is glued from translated pieces`.

### Task 2: The five messages

**Files:**
- Modify: `qtui/qml/GameListScreen.qml` (the instruction Text, and give it `objectName: "gamelist_intro"`), `qtui/qml/ChoiceSummary.qml:28`, `qtui/qml/NavItem.qml:19`, `qtui/qml/HomeScreen.qml:78`, `qtui/cases.py` (`case_label`), `qtui/i18n_pt_br.py`, `docs/CHANGELOG.md`
- Test: `tests/test_qtui.py` (existing classes: `GameListScreen` for the instruction, the class holding `test_every_navigation_item...` accessibility checks near line 3660 for the menu, the classes that read `groupName` and `selectedLabel` for the case name), `tests/test_i18n.py`

**Interfaces:**
- Consumes: Task 1's tests (they must pass at the end); `case_label(case) -> str` in `qtui/cases.py` (same signature, same results).
- Produces: new messages (English → Portuguese):
  - `"Steam keeps your game list on a web page. Open it and log in if asked. A page of text appears: press %1 and save it, keeping the name userdata.json. The app notices the file by itself."` → `"A Steam guarda a sua lista de jogos em uma página da web. Abra-a e entre, se pedir. Aparece uma página de texto: aperte %1 e salve, mantendo o nome userdata.json. O programa percebe o arquivo sozinho."`
  - `"Steam case, %s"` → `"Case da Steam, %s"`
  - `"%1: %2. Change"` → `"%1: %2. Mudar"`
  - `"%1, locked"` → `"%1, bloqueado"`, `"%1, done"` → `"%1, concluído"`
  - `"%1, %2"` → `"%1, %2"`
  The old pieces are removed from the Portuguese table.

- [ ] **Step 1: Write the failing tests (they pin the texts, so they should pass before and after, except where a key is new).**
  - In `GameListScreen`: `test_the_instruction_has_the_key_of_this_computer_in_the_middle`: the text of `gamelist_intro` equals the English sentence with `Ctrl+S` or `Cmd+S` (whatever `qtui.system.SAVE_KEY` is) in place of `%1`; and the same with the language set to `pt-BR` equals today's Portuguese put together.
  - Accessibility names, through `QAccessible` as the existing test at line 3660 does: a menu step with a hint that is locked reads `3. 100% games (optional), locked`; a done step without a hint reads `1. Game list, done`; one chosen-look chip reads `<label>: <value>. Change`; a Home step reads `<label>, <state>`. In Portuguese, the same with `bloqueado`, `concluído`, `Mudar`.
  - `case_label` for a colour reads `Steam case, red`, for a custom colour `Steam case, custom colour`; in Portuguese `Case da Steam, vermelho` and `Case da Steam, cor personalizada` (use the strings the existing tests expect today; the existing assertions at the lines that read `groupName` and `selectedLabel` already cover English).
- [ ] **Step 2: Run the new tests and Task 1's tests.** Expected: Task 1's FAIL still; the new text tests PASS (same text) or FAIL only where they need `gamelist_intro`, which does not exist yet.
- [ ] **Step 3: Change the five places and the Portuguese table** as in the Produces block: `qsTr("...%1...").arg(saveKey)`, `qsTr("%1: %2. Change").arg(modelData.label).arg(modelData.value)`, in `NavItem.qml` the name without the state first (`label` plus the hint) and then `qsTr("%1, locked").arg(base)` or `qsTr("%1, done").arg(base)` or `base`, `qsTr("%1, %2").arg(modelData.label).arg(screen.stateText[modelData.state])`, and in `case_label` `tr("Steam case, %s") % found.lower()`. Add one line to the changelog under a "### 📝 Behind the scenes" heading in Unreleased (the heading is not there yet).
- [ ] **Step 4: Run `tests.test_i18n` and the new text tests.** Expected: PASS, including Task 1's two tests and the "nothing missing / nothing left over" pair.
- [ ] **Step 5: Commit** `refactor(qtui): five messages are one sentence each, with a blank for the part that changes`.

### Task 3: Whole suite and the owner's look

**Files:** none besides notes.

- [ ] **Step 1: Run the whole suite.** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests`. Expected: OK, no failures. Report the count.
- [ ] **Step 2: Run `.venv/bin/python -m qtui --selftest`.** Expected: `selftest ok`.
- [ ] **Step 3: Update `claude-projects/steam-case-covers/CONTEXT.md`** (item 6 of the UI work plan, "Current state") and add a short paragraph to `LOG.md`; commit there on `main`.
- [ ] **Step 4: Tell the owner what is not checked** (the real window in both languages, macOS, Windows beyond CI) and ask them to look at step 1 and the Case step in English and Portuguese, then run `/thermo-nuclear-code-quality-review`. Do not say "good to push".
