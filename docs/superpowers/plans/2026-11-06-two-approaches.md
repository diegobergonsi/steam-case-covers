# Two approaches, made clear: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline, one task at a time, test first, commit per task). Steps use `- [ ]`.

**Goal:** Home shows two equal path cards (automatic leads), and the left menu names the path you are in.

**Architecture:** `Shell` gains three small members (`stepCount`, `canSwitch`, `startPath`); a new `PathCard.qml` component replaces the "Step by step" and "Pick games by hand" sections and the filled footer of `HomeScreen.qml`; `Main.qml` shows a heading in the navigation. Text is in QML `qsTr`, translated in `qtui/i18n_pt_br.py`.

**Tech stack:** Python 3, PySide6 / Qt Quick, unittest (`QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest`).

**Spec:** `docs/superpowers/specs/2026-11-06-two-approaches-design.md`

## Global constraints
- Conventional Commits, no attribution lines, never push. Branch `feat/home-two-approaches`.
- Test first. The suite stays green with and without Qt.
- Refinement, not redesign: tokens only from `Theme.qml`, no new colour or font, sky blue stays the one voice. Before the first QML edit, read `~/.claude/plugins/cache/impeccable/impeccable/4.7.0/skills/impeccable/reference/craft-floor.md` and follow it.
- Touch targets 44 px or more, nothing hover-only, 640 px minimum width, 800 px height, keyboard and screen-reader names.
- Public text never mentions Flatpak, Flathub or AUR. No screenshot of the real window or real Steam account is kept: a fake HOME with a fake Steam only.

## Review Focus
1. A wider font (Windows) wraps a long card title; the card grows and both cards stay the same height. Test: set a long title, both cards' heights are equal and no text is cut.
2. The switch is blocked while Make or Apply runs: the click is ignored, the other card says "Wait until this finishes", and the card is usable again when the run ends.
3. Changing language while on Home updates card titles, cue and the nav heading at once.
4. At 640 px wide the cards stack and nothing is wider than the section; at the new minimum height the manual path's seven rows plus the heading do not touch the footer links.
5. Plural step counts: "1 step" and "5 steps"; Portuguese "1 passo", "5 passos".

---

### Task 1: Shell: step counts, switch guard, one entry for a card

**Files:**
- Modify: `qtui/shell.py` (add after `startNatural`, around line 85)
- Test: `tests/test_qtui.py`, class `ShellHome` (around line 4629)

**Interfaces:**
- Produces: `Shell.stepCount(flow: str) -> int` (slot; steps without Home: 5 for "natural", 6 for "manual"); `Shell.canSwitch -> bool` (property, notify `switchChanged`; false while `make.running` or `apply.busy`); `Shell.startPath(flow: str)` (slot): other flow -> `_switch(flow)`; same flow -> `go(resume)`.

- [ ] **Step 1: Failing tests** in `ShellHome`: `test_step_counts_are_five_and_six` (`stepCount("natural") == 5`, `("manual") == 6`); `test_start_path_on_the_other_flow_switches_and_leaves_home` (`startPath("manual")` -> `flow == "manual"` and `current == resume`); `test_start_path_on_the_same_flow_goes_to_the_step_to_continue` (first visit: `current == 1`); `test_can_switch_follows_make_and_apply` (`sh.make._set_state(running=True)` -> `canSwitch` False and `switchChanged` emitted; `startPath("manual")` leaves `flow == "natural"`; set `running=False` -> True; do the same for `apply.busy` the way the nearby Apply tests make it busy).
- [ ] **Step 2: Run to fail:** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest tests.test_qtui.ShellHome -v`. Expected: AttributeError.
- [ ] **Step 3: Implement** the three members; emit `switchChanged` from `make.runningChanged` and `apply.canApplyChanged` (connect in `__init__`).
- [ ] **Step 4: Run to pass**, then the whole `ShellHome`.
- [ ] **Step 5: Commit** `feat(qtui): the shell knows its step counts and when a path can be switched`.

### Task 2: Home: two path cards

**Files:**
- Create: `qtui/qml/PathCard.qml`; register it in `qtui/qml/qmldir`.
- Modify: `qtui/qml/HomeScreen.qml`; `qtui/qml/Theme.qml` (add `pathCardMinWidth: 260`).
- Test: `tests/test_qtui.py`, class `HomeScreen` (around 4670) and the by-hand test around line 6912.

**Interfaces:**
- Consumes: Task 1 members.
- Produces: `PathCard` with properties `string title, line, steps, cue, tag`, `bool lead, blocked`, signal `activated()`; objectNames `home_card_natural`, `home_card_manual` (inner `<name>_tag`, `<name>_cue`); Home sections `home_section_paths` (cards) and `home_section_progress` (returning only; the old `home_section_main`).

- [ ] **Step 1: Failing tests**, replacing the old Home tests that name `home_main`, `home_section_main`, `home_manual`, `home_natural` (lines 4691-4702, 4779-4785, 6912-6922):
  - first visit: titles "The same case for every game on your list" and "Pick games, choose their cases"; steps "5 steps" and "6 steps"; cues "Start →" on both; `home_card_natural.lead` True, manual False; tag "Best for most people" only on natural; `self.has("home_main")` False; `home_restore` is not filled.
  - click `home_card_natural` -> `shell.current == 1`; click `home_card_manual` -> `shell.flow == "manual"` and `current == shell.resume`.
  - returning (covers on disk): the card of `shell.flow` says "Continue →", the other "Start →"; `home_section_progress` heading "Your progress: Same case"; `home_row_*` and `home_state_*` behave as before.
  - blocked: with `make._set_state(running=True)` the other card's cue is "Wait until this finishes", a click leaves the flow unchanged; after `running=False` the cue is "Start →" again.
  - keyboard: focus a card, Enter and Space activate it; role Button; name contains title and steps.
  - layout: at the window's default width the cards share one `y` and are equal height; at 640 px width they stack (equal `x`) and no card is wider than `home_section_paths`.
- [ ] **Step 2: Run to fail.**
- [ ] **Step 3: Implement `PathCard.qml`** as a transparent `Rectangle` (radius `Theme.radiusCard`, border `Theme.edge` 1 px, or `Theme.accent` 2 px when `lead`), an inner column: tag pill (lead only, small text), title (bold, section size, wraps), line (muted, wraps), steps and cue on one row (small, cue in `Theme.accent` for the lead card else `Theme.text`). `activeFocusOnTab`, focus ring `Theme.focusRing` in `Theme.text`, Return/Enter/Space as in the Home rows, pressed = opacity 0.85, no hover-only state, height at least 44 px.
- [ ] **Step 4: Rebuild `HomeScreen.qml`:** the cards section is headed `qsTr("Choose your way")` (planner's call), holding one `Grid` (columns 2 when the section is at least `2 * Theme.pathCardMinWidth + Theme.s16` wide, else 1) with the two cards; both cards take the larger implicit height; remove the old manual section, the footer, and the "Five short steps" text; the progress section heading is `qsTr("Your progress: %1").arg(<same short path name the nav uses>)`. Card click calls `shell.startPath(flow)`; `blocked` = other flow and `!shell.canSwitch`.
- [ ] **Step 5: Run** `HomeScreen` and the by-hand tests; all pass.
- [ ] **Step 6: Commit** `feat(qtui): Home shows the two ways to make covers as two cards`.

### Task 3: Navigation heading

**Files:**
- Modify: `qtui/qml/Main.qml` (nav column and highlight, lines 40-96); `qtui/qml/Theme.qml` (`navHeadingHeight: 24`, `windowMinHeight` 528 -> 552 with its comment).
- Test: `tests/test_qtui.py` (nav tests near 4821-4850 and 7231).

**Interfaces:** objectName `nav_flow` (the heading text, role Heading) between `nav_home` and the next step.

- [ ] **Step 1: Failing tests:** `nav_flow` text is "Same case · 5 steps" in the natural flow and "Pick games · 6 steps" after `startManual()` (and "1 step" for a singular, if reachable via the plural key); it sits below `nav_home` and above the second step; the selection highlight stays aligned with the selected row for current 0, 1 and the last step in both flows; in the manual flow the last step's bottom is at or above `footer_discord`'s top at `Theme.windowMinHeight`; the existing height assertion on `windowMinHeight` still passes.
- [ ] **Step 2: Run to fail.**
- [ ] **Step 3: Implement:** each nav delegate becomes a small Column: a heading `Text` shown only for `index === 1` (height `Theme.navHeadingHeight`, 0 otherwise; small muted text; `Accessible.role: Accessible.Heading`) above the `NavItem`; highlight `y` adds `Theme.navHeadingHeight` when `shell.current > 0`; heading text `(shell.flow === "manual" ? qsTr("Pick games") : qsTr("Same case")) + " · " + qsTr("%n step|%n steps", "", shell.stepCount(shell.flow))`.
- [ ] **Step 4: Run** nav tests and the whole `HomeScreen`; pass.
- [ ] **Step 5: Commit** `feat(qtui): the navigation says which way you are on`.

### Task 4: Portuguese, docs, changelog

**Files:**
- Modify: `qtui/i18n_pt_br.py`; `docs/ui-guide.md` (line 7 and the Home rules); `docs/DESIGN.md` (components: `PathCard`; the 24 px heading); `docs/CHANGELOG.md` `[Unreleased]`.
- Test: `tests/test_i18n.py` (it already checks the table against `tools/i18n_keys.py`).

- [ ] **Step 1: Failing test:** run the i18n tests; they report the new keys missing. Add one assertion that "%n step|%n steps" translates to "1 passo" for 0 and 1 and "5 passos" for 5.
- [ ] **Step 2: Add the entries** (feminine "case"): "The same case for every game on your list" -> "A mesma case para todos os jogos da sua lista"; "Choose a look once. Every game on your list gets it." -> "Escolha um visual uma vez. Todo jogo da sua lista recebe."; "Pick games, choose their cases" -> "Escolha os jogos e as cases"; "Put games in groups and give each group its own case." -> "Coloque os jogos em grupos e dê a cada grupo a sua case."; "%n step|%n steps" -> "%n passo|%n passos"; "Same case" -> "Mesma case"; "Pick games" -> "Escolher jogos"; "Best for most people" -> "A melhor para a maioria das pessoas"; "Start →", "Continue →" if not present; "Wait until this finishes" -> "Espere isto terminar"; "Your progress: %1" -> "O seu progresso: %1"; the section heading text chosen for the cards ("Choose your way" -> "Escolha o seu caminho"). Remove keys no longer used (the old manual section texts, "Five short steps...", "Pick games by hand", "Back to step by step", "Step by step") if no other screen uses them (`tools/i18n_keys.py` shows it).
- [ ] **Step 3: Docs:** ui-guide (the navigation shows a heading with the path name and step count; Home has two cards and no filled button; "one filled button" applies to screens with a footer), DESIGN.md components, CHANGELOG line in plain words.
- [ ] **Step 4: Run** `tests.test_i18n` and the whole suite (`QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests`, about 4 minutes); all green; `.venv/bin/python -m qtui --selftest` prints `selftest ok`.
- [ ] **Step 5: Commit** `feat(qtui): Portuguese and docs for the two ways`.

### Task 5: Look at it, polish, review, report

- [ ] **Step 1: Render** Home (welcome and returning) and one screen of each path with the fake HOME and fake Steam at 640x600, the default size and 1280x800, in English and Portuguese. Look at every image. Fix what shows (a batch, then look again). Delete the images afterwards unless the owner asks to keep them.
- [ ] **Step 2: Run `/impeccable polish`** on `HomeScreen.qml`, `PathCard.qml`, `Main.qml`; fix every finding the way the project's rules ask (test first for what a test can show).
- [ ] **Step 3: Run `/thermo-nuclear-code-quality-review`** on the branch. Fix every finding, minor ones too (a test first where a test can show it). If the skill is not installed, say so and ask.
- [ ] **Step 4: Update** `claude-projects/steam-case-covers/CONTEXT.md` ("Current state", "Open items"), `LOG.md` and `FEATURES.md`; commit there on `main`.
- [ ] **Step 5: Report** to the owner: what was fixed, what is open and why, what was not verified (Windows fonts, Deck touchscreen, macOS), and that the branch is good to push. Do not push.

## Items 2 to 6 (not in this plan)
Cases screen layout; end of Apply with undo and result; touch targets (and settle 44 or 36 in the docs); contrast of the faint text and the control edge on raised fills; copy and translation of joined sentences. Each gets its own spec and plan, and each ends with `/thermo-nuclear-code-quality-review` before "good to push".
