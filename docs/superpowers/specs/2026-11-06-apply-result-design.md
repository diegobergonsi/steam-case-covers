# The end of Apply, clearer: design

Date: 2026-11-06. Origin: item 3 of 6 of the UI work plan that came out of an Impeccable critique of the whole window (score 27/40), and a design interview with the owner (a mockup helped them decide). Items 1 (two ways on Home, PR #47) and 2 (Cases screen, PR #48) are merged.

## Problem
After "Apply to Steam" the whole answer is one long grey sentence with a file path ("Done. 3 covers added to the Steam account “X” (0 replaced older art, 0 already up to date). Backup saved in: /path… Start Steam to see the change."). It shows no picture of what was added, and Undo exists only on Home, below other sections. Home also shows an Undo card with greyed buttons to people who have nothing to undo.

## Goal
The person sees at once that it worked, what was added, what to do next, and can undo right there. The same kind of message looks the same wherever it appears.

## Decisions (all confirmed by the owner)
- **After a successful Apply, one "Done" card** on the Add screen replaces "Before you apply" and "Result":
  - Big line, in the Done green: "%n cover added to “Player”." (no check-mark glyph).
  - A row of the added covers' pictures: the same first covers the Make screen shows (new shared component `CoverThumbs`), no "and N more".
  - A line: "Start Steam to see them." or "Steam is starting." (or "Could not start Steam (…). Please open it yourself.").
  - A small grey line the person can select with the mouse: "0 replaced older art, 0 already up to date. Backup saved in: …" plus the sentence about art set by hand in Steam when it applies.
  - A quiet **"Undo"** button. It asks the same question as Home's "Restore previous artwork". It shows once an undo is possible.
  - The footer keeps one blue button: "Go to Home →".
- **"Nothing to change":** the card says "Nothing to change." and "All %n covers were already in the Steam account “Player”." with **no Undo** (and the restart line if Steam was asked to restart).
- **Apply fails:** the screen stays as today: "Before you apply" and "Result" with a red message and the existing box.
- **After "Undo"** (from the card or from Home): the Add screen goes back to the "before" state with "Apply to Steam", and the sentence "Restored your previous artwork (12 files)…" is a **toast**.
- **Home:** the results of Restore and Reset are toasts too, same sentences as today. The line inside Home's Undo card stays only for progress ("Closing Steam…") and errors. A toast is not shown for an Apply (the Done card says it).
- **Home's Undo card hides while there is nothing to undo** (no backup, no covers of this app, nothing running). With two or more Steam accounts it always shows, because the account is chosen in it.
- **Toast:** it stays 4 seconds plus about 50 ms per character, at most 12 seconds, so a long sentence can be read (planner's call). The sentences are today's, no new wording.
- The texts of the card are built when they are read, not saved as strings, so a change of language updates them.
- Portuguese uses the feminine "case". Strings are in the plan.

## Not in this spec
How backups work, how covers are copied, the Make screen's behaviour (it only gets the shared thumbnails component), touch sizes, contrast, copy of other screens (items 4 to 6).

## Constraints
640 px minimum width, 800 px height on the Deck, English and Brazilian Portuguese, keyboard, screen-reader names, touch target of 44 px or more for the new button, every size from `Theme.qml`, no new colour or font, a new component goes into `docs/ui-guide.md` first. Refinement: keep the identity of the window.
