# The end of Apply, clearer: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline, one task at a time, test first, commit per task). Steps use `- [ ]`.

**Goal:** a "Done" card with the covers and an Undo on the Add screen; Restore and Reset results as toasts; Home's Undo card hidden while there is nothing to undo.

**Architecture:** `Apply` (Python) keeps its `status` text exactly as today, and gains a `result` (read when asked, so it follows the language), `hasResult`, and a toast for a finished Restore or Reset; `Toast` shows long texts longer; a new `CoverThumbs.qml` is shared by Make and Add; `AddScreen.qml` and `HomeScreen.qml` change. Text is in `qsTr` / Python `tr`, translated in `qtui/i18n_pt_br.py`.

**Tech stack:** Python 3, PySide6 / Qt Quick, unittest (`QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest`).

**Spec:** `docs/superpowers/specs/2026-11-06-apply-result-design.md`

## Global constraints
- Conventional Commits, no attribution lines, never push. Branch `feat/apply-result`.
- Test first. The suite stays green with and without Qt.
- Refinement, not redesign: tokens only from `Theme.qml` (no loose numbers: `Theme.s8 + 2` fails the Tokens test), no new colour or font, no new glyph used as an icon. Before the first QML edit, read `~/.claude/plugins/cache/impeccable/impeccable/4.7.0/skills/impeccable/reference/craft-floor.md`.
- Touch target 44 px or more for the new button (`Theme.touchMin`), nothing hover-only, 640 px width, 800 px height, keyboard and screen-reader names.
- **Lessons from PRs #47 and #48:** (1) a test that changes text or the window size and then checks positions waits with `self.wait_for(...)` (it is in `QtCase`); (2) never cut tests with a script: after editing `tests/test_qtui.py` check the list of `def test_` lines added and removed in `git diff`; (3) before removing or renaming an object name, grep the whole repo (`qtui/__main__.py` selftest, docs, tools); (4) a change of language fires every property's notify signal: anything that clears state on a "library changed" style signal must compare with the last value first; (5) texts built in Python are built when read, not stored.
- Public text never mentions Flatpak, Flathub or AUR. No screenshot of the real window or real Steam account is kept; render only with a fake HOME and fake Steam, then delete the images.

## Review Focus
1. The card for every outcome: done with 1 and with many covers, with and without the hand-set-art sentence, Steam restarted, Steam asked to restart but failed, Steam not asked; "Nothing to change" with 1 and with many; the Undo button only for "done".
2. Undo from the card: the question opens; Cancel changes nothing; after confirming, the screen is back in the "before" state, a toast shows the sentence, and no duplicate sentence stays in the Result card.
3. Home: the Undo card is hidden with one account and nothing to undo, always shown with two or more accounts, shown while a job runs; Restore and Reset show a toast, and the line inside the card stays only for progress and errors.
4. A change of language while the Done card or a toast is on screen updates the card (not the toast already shown).
5. 640 px wide with a long account name and a long backup path: nothing leaves the window, the pictures wrap, the new button is at least 44 px.

---

### Task 1: Apply model: the result, and toasts for Restore and Reset

**Files:**
- Modify: `qtui/apply.py` (`_work`, `_go`, `_on_finished`, `_make_changed`, new properties and a pure helper).
- Test: `tests/test_qtui.py`, class `ApplyState` (about line 5931; reuse its helpers `covers_ready()`, `go()`, `self.result`, `self.log`).

**Interfaces:**
- Produces: `Apply.result -> dict` (property, `QVariantMap`, notify `resultChanged`): `{}` when there is none, else `{"kind": "done" | "nothing", "title", "line", "details"}` (strings, built from the stored facts each time it is read); `Apply.hasResult -> bool` (notify `resultChanged`); signal `resultChanged`. A pure module function `result_card(info: dict) -> dict` builds the strings from `info = {"kind", "applied", "replaced", "unchanged", "account", "backup", "jpg_moved", "restart": "no" | "started" | "failed", "error": str}`.
- Behaviour: the worker fills `job["result"]` with that `info` for an apply (kind "done" when `r["applied"]`, else "nothing"); `_on_finished` keeps it as `self._result_info` for an apply that succeeded; it is cleared when a new job starts (`_go`) and where `_make_changed` clears the status. `status` and `statusKind` stay exactly as today. On a finished **restore or reset** without an error, `self._shell.toast.emit(text)` is also called with the same `text` the status gets.
- Texts (English; `trn` fills `%n`): done title `trn("%n cover added to “%s”.|%n covers added to “%s”.", applied) % account`; done line `tr("Steam is starting.")` when restart is "started", `tr("Could not start Steam (%s). Please open it yourself.") % error` when "failed", else `tr("Start Steam to see them.")`; done details `tr("%d replaced older art, %d already up to date.") % (replaced, unchanged)` + " " + `tr("Backup saved in: %s") % backup` + (when `jpg_moved`) " " + the existing `trn("Art you had set by hand in Steam (%n game) was moved into the backup; Restore brings it back.|...", jpg_moved)`; nothing title `tr("Nothing to change.")`, nothing line `trn("The cover was already in the Steam account “%s”.|All %n covers were already in the Steam account “%s”.", unchanged) % account` followed, only when restart is "started" or "failed", by the restart sentence above, details "".

- [ ] **Step 1: Failing tests** in `ApplyState`: `test_a_done_result_has_a_title_a_line_and_details` (after `go()`: `hasResult`, `result["kind"] == "done"`, title "2 covers added to “Alice”.", line "Steam is starting." with the default restart switch, details "0 replaced older art, 0 already up to date. Backup saved in: /b"); `test_the_result_line_when_steam_is_not_asked_to_start` (`setSwitch("restart_steam", False)` -> "Start Steam to see them."); `test_the_result_line_when_steam_cannot_start` (the existing test around line 6138 shows how to make `start_steam` fail); `test_the_result_mentions_art_set_by_hand` (the case of line 6130); `test_nothing_to_change_has_its_own_card` (kind "nothing", title "Nothing to change.", line "All 2 covers were already in the Steam account “Alice”."); `test_one_cover_reads_in_the_singular`; `test_no_result_after_a_failure_a_restore_or_a_reset_and_it_goes_when_new_covers_come`; `test_restore_and_reset_send_a_toast_with_the_status_sentence` (connect `shell.toast`; after a restore and a reset the list holds exactly the status text; an apply sends none; an error sends none); `test_the_result_follows_a_change_of_language` (finish an apply in English, `i18n.set_language("pt-BR")`, read `result["title"]` -> Portuguese; add a cleanup that sets "en" back; the Portuguese strings come in Task 5, so write the assertion on the title only after Task 5 or mark the assertion with the key and add it in Task 5).
- [ ] **Step 2: Run to fail:** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest tests.test_qtui.ApplyState -v`.
- [ ] **Step 3: Implement** `result_card`, the worker fill, the properties, the clearing, and the toast; leave `status` untouched (the existing `ApplyState` tests about `status` keep passing).
- [ ] **Step 4: Run to pass**, then the whole `ApplyState`, `HomeScreen` and `AddScreen`.
- [ ] **Step 5: Commit** `feat(qtui): Apply keeps a result card for the Add screen and toasts for Restore and Reset`.

### Task 2: Two components: longer toasts and CoverThumbs

**Files:**
- Modify: `qtui/qml/Toast.qml`, `qtui/qml/Theme.qml` (`toastCharMs: 50`, `toastMaxMs: 12000`), `qtui/qml/MakeScreen.qml` (use `CoverThumbs`), `qtui/qml/qmldir`, `docs/ui-guide.md`, `docs/DESIGN.md`.
- Create: `qtui/qml/CoverThumbs.qml`.
- Test: `tests/test_qtui.py`, class `Components`.

**Interfaces:**
- Produces: `Toast` keeps `showMs` as the minimum; the time shown is `Math.min(Theme.toastMaxMs, showMs + message.length * Theme.toastCharMs)` (expose it as `readonly property int shownMs`, used by the timer). `CoverThumbs`: a `Flow` with `property var model` (list of file URLs) and `property string prefix` (the objectName start of each picture, e.g. `"make_thumb_"`); each picture is the Image of `MakeScreen.qml` today (size `Theme.thumbWidth` by `Theme.thumbHeight`, `cache: false`, role Graphic, name "Cover N"); `visible` only when the model is not empty.

- [ ] **Step 1: Failing tests** (`Components`): `test_a_long_toast_stays_longer_but_not_forever` (short text -> `shownMs == showMs + len*50`; a 400-character text -> 12000; the timer interval equals it); `test_cover_thumbs_show_the_pictures_and_wrap` (a model of 5 file URLs in a 300 px wide harness: five images named `<prefix>0..4`, none beyond the width, more than one row; an empty model is not visible; each has role Graphic and a name).
- [ ] **Step 2: Run to fail.**
- [ ] **Step 3: Implement**; replace the inline thumbnails of `MakeScreen.qml` with `CoverThumbs { objectName: "make_thumbs"; prefix: "make_thumb_"; model: screen.make.thumbs; width: parent.width }`; add both to the guide and DESIGN.md.
- [ ] **Step 4: Run to pass**, then `Components`, `MakeScreen`, `Tokens` (the existing Make thumbnail tests must still pass unchanged).
- [ ] **Step 5: Commit** `feat(qtui): toasts stay as long as they take to read, and one component for the cover pictures`.

### Task 3: The Add screen: the Done card

**Files:**
- Modify: `qtui/qml/AddScreen.qml`; the Add tests in `tests/test_qtui.py` class `AddScreen` (about lines 4560 to 4730).
- Test: the same class.

**Interfaces:**
- Consumes: Task 1 (`result`, `hasResult`, `canRestore`, `restore()`) and Task 2 (`CoverThumbs`).
- Produces objectNames: `add_section_before` and `add_section_result` (visible only while `!apply.hasResult`; `add_status` text = `status` when it is not empty and its kind is not "ok", else `readyText`); `add_section_done` (heading "Done", visible when `apply.hasResult`) holding `add_done_title` (colour `Theme.done`, bold, section size), `add_thumbs` (`CoverThumbs`, prefix `add_thumb_`, model `shell.make.thumbs`), `add_done_line`, `add_done_details` (a read-only `TextEdit`, `selectByMouse`, small muted text, wrapping anywhere), `add_undo` (`QuietButton` "Undo", visible when `result.kind === "done" && apply.canRestore`, calls `apply.restore()`); `add_main` unchanged.

- [ ] **Step 1: Failing tests** (update the old ones and add): before Apply the screen is as today (sections `add_section_before`, `add_section_result`, `add_status` "2 covers are ready to add.", `add_section_done` not visible); after Apply (same flow as the test at line 4660): `add_section_before` and `add_section_result` are hidden, `add_section_done` visible, `add_done_title` "2 covers added to “Alice”.", `add_done_line`, `add_done_details` start "0 replaced older art, 0 already up to date. Backup saved in: ", `add_thumb_0` exists when covers exist, `add_main` reads "Go to Home →" and is the only filled button, `add_undo` visible once `canRestore` (wait for the probe); "nothing to change": the card has no `add_undo`; after Apply fails the old sections and a red `add_status` stay; clicking `add_undo` opens the apply dialog with the restore question, Cancel changes nothing, confirming returns to the before state (`add_section_done` hidden, `add_main` "Apply to Steam") with a toast text equal to `apply.status`, and `add_status` back to the ready text (the "ok" sentence is not repeated there); at 640 px with a 40-character account name and a 120-character backup path nothing is wider than the window (use `wait_for`); `add_undo` is at least 44 px high; `add_done_details` can be selected (`selectByMouse` is true, `readOnly` is true).
- [ ] **Step 2: Run to fail:** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest tests.test_qtui.AddScreen -v`.
- [ ] **Step 3: Rebuild `AddScreen.qml`** as above, keeping the focus rule (one footer button so the keyboard focus stays) and `Component.onCompleted` / `onDestruction`.
- [ ] **Step 4: Run to pass**, then `AddScreen`, `MakeAddFlow`, `Tokens`, `Entry`; run the selftest.
- [ ] **Step 5: Commit** `feat(qtui): the Add screen shows what was added, with Undo in place`.

### Task 4: Home: toasts, and an Undo card only when there is something to undo

**Files:**
- Modify: `qtui/qml/HomeScreen.qml`; the Home tests in `tests/test_qtui.py` class `HomeScreen` that read the greyed Undo buttons or `home_status`.
- Test: the same class.

**Interfaces:**
- Consumes: Task 1 (toast on Restore and Reset).
- Behaviour: `home_section_undo` is visible when `apply.canChoose || apply.canRestore || apply.canReset || apply.busy || apply.asking`; `home_status` is visible when its text is not empty and `apply.statusKind !== "ok"`.

- [ ] **Step 1: Failing tests:** with one account and nothing to undo (`undo_ready(backup=False)` style) the card is hidden; with a backup it shows and the buttons are enabled; with two accounts it shows even with nothing to undo; while a restore runs it shows; after a restore Home shows a toast with the sentence and `home_status` is hidden; a reset likewise; an error keeps the line visible and red; progress ("Closing Steam…") shows in the line; update the existing tests that expect the greyed buttons or the "Restored…" line in `home_status` (lines near 5022 and the tests named `...greyed_until...`, `...hint...`), changing what they assert, never deleting a behaviour test without replacing it.
- [ ] **Step 2: Run to fail.**
- [ ] **Step 3: Implement** the two bindings.
- [ ] **Step 4: Run to pass**, then `HomeScreen`, `AddScreen`, `ApplyState`, `Tokens`; selftest.
- [ ] **Step 5: Commit** `feat(qtui): Home shows its Undo card only when there is something to undo, and says the results in a toast`.

### Task 5: Portuguese, docs, changelog

**Files:**
- Modify: `qtui/i18n_pt_br.py`; `docs/ui-guide.md` (the Add step and where Undo lives); `docs/CHANGELOG.md` `[Unreleased]`; `README.md` and `README.pt-BR.md` where they describe the Result line or Home's Undo (grep "Restore previous artwork", "Undo").
- Test: `tests/test_i18n.py` (compares the table with `tools/i18n_keys.py`; remove keys no code uses).

- [ ] **Step 1: Failing test:** `tests.test_i18n` lists the missing keys; add the pending assertion of `test_the_result_follows_a_change_of_language` from Task 1 (the Portuguese title "2 capas adicionadas a “Alice”.").
- [ ] **Step 2: Add the entries** (feminine "case"): "%n cover added to “%s”.|%n covers added to “%s”." -> "%n capa adicionada a “%s”.|%n capas adicionadas a “%s”."; "Start Steam to see them." -> "Abra a Steam para ver as capas."; "Steam is starting." -> "A Steam está iniciando."; "Could not start Steam (%s). Please open it yourself." -> "Não foi possível iniciar a Steam (%s). Abra-a você mesmo."; "%d replaced older art, %d already up to date." -> "%d substituíram arte antiga, %d já estavam em dia."; "Backup saved in: %s" -> "Backup salvo em: %s"; "Nothing to change." -> "Nada a mudar."; "The cover was already in the Steam account “%s”.|All %n covers were already in the Steam account “%s”." -> "A capa já estava na conta “%s” da Steam.|Todas as %n capas já estavam na conta “%s” da Steam."; "Undo" -> "Desfazer" (it exists: reuse); "Done" -> "Pronto" (exists). Keep the wording style of the neighbouring entries.
- [ ] **Step 3: Docs and changelog** in plain words.
- [ ] **Step 4: Run** the whole suite (`... unittest discover -s tests > <log> 2>&1`, read `Ran`/`OK`/`FAILED` from the log, about 4 minutes) and the selftest; all green.
- [ ] **Step 5: Commit** `feat(qtui): Portuguese and docs for the end of Apply`.

### Task 6: Look at it, review, report

- [ ] **Step 1: Render** the Add screen (before; Done with covers; Done with a long account name and path at 640 px; Nothing to change; after Undo with the toast) and Home (nothing to undo; something to undo; a toast) with a fake HOME and fake Steam at 640x552, 900x640 and 1280x800, in English and Portuguese, using `QT_QPA_PLATFORM=offscreen` on a scratch copy of the QML where `Card.qml` and `PreviewCard.qml` have the shadow effect removed (the real effect draws blank offscreen; xcb crashes in the Claude sandbox). Look at every image, fix what shows, delete the images.
- [ ] **Step 2: Review with the thermo-nuclear standards.** `/thermo-nuclear-code-quality-review` is user-only; read `~/.claude/skills/thermo-nuclear-code-quality-review/SKILL.md` and dispatch a fresh reviewer on Opus (the owner's choice for big changes) with it, the review package, the spec, this plan, the Review Focus and the ledger rulings. Fix every finding, minor ones too (a test first where a test can show it), unless it needs the owner's decision (then ask one short question at the end). Run the whole suite again.
- [ ] **Step 3: Update** `claude-projects/steam-case-covers/` (`CONTEXT.md` current state and open items, `LOG.md`, `FEATURES.md`, `ARCHITECTURE.md`); commit there on `main`.
- [ ] **Step 4: Report** to the owner: what was fixed, what is open and why, what was not verified (Windows fonts, Deck touchscreen, macOS, a real screen reader), and that the branch is good to push. Do not push. After the owner pushes, open the PR with a simple description (plain words, a few emojis, no attribution line) when asked.

## Items 4 to 6 (not in this plan)
Touch targets (settle 44 or 36 in the docs; `Theme.touchMin` = 44 exists now); contrast of faint text and control edge on raised fills; copy and joined sentences. Each gets its own spec and plan.
