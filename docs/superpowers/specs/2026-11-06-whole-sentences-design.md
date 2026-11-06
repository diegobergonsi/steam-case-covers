# Whole sentences for translation: design

Date: 2026-11-06. Origin: item 6 of 6 of the UI work plan from the Impeccable critique (score 27/40) and a short interview with the owner, who reads and writes Brazilian Portuguese and said no message sounds odd or confusing to them. Items 1 to 5 are merged (#47 to #52).

## Problem
A few messages are built from pieces glued together in the code, and each piece is translated on its own. The translator cannot move a word, a key name or a colour name to where the other language wants it. Today the Portuguese happens to work, because it follows the English order, but any language that needs another order (or a better Portuguese sentence) cannot be done without changing code.

The pieces that do this (found by searching the whole window):

| Where | What is glued | Pieces now |
|---|---|---|
| Step 1 instruction (`GameListScreen.qml`) | the shortcut to save a page, in the middle of a sentence | "…press " + `Ctrl+S` + " and save it…" |
| Name of a group's case (`cases.py`) | a colour name | "Steam case, " + the colour in lowercase |
| Screen reader name of a chosen look (`ChoiceSummary.qml`) | an ending | label + ": " + value + ". Change" |
| Screen reader name of a menu step (`NavItem.qml`) | an ending | label + hint + ", locked" or ", done" |
| Screen reader name of a step on Home (`HomeScreen.qml`) | a state word | label + ", " + state |
| Question before replacing covers (`reasons.py`) | a clause in the middle of a sentence | "You chose no highlight … case): " + clause + "." (added during the work: the guard test found it) |

Whole sentences joined by a space (the lines of the Make step, the "Done" card details, the reasons in questions) are **not** a problem: each part is a complete sentence and can be translated as it is.

## Goal
Each of the six places above is one message with a blank where the changing part goes, the way the games page help already works (`PAGE_HELP_TEMPLATE % SAVE_KEY`). The words in English and in Portuguese stay as they are today; only where the pieces are cut changes.

## Decisions

Confirmed by the owner:
- **Option A:** fix only the pieces that force a word order. The joins of whole sentences stay as they are (option B was a bigger change touching many texts, and the owner said the wording is fine).

The planner's calls (the owner can change them):
- The English text of every message stays the same, word for word, including the screen reader names. The Portuguese text is today's text with the same words, now in one message each.
- In the QML files a blank is written `%1`, `%2` and filled with `.arg(...)` (the usual Qt way). In Python it is `%s`, as everywhere else in the app.
- The colour name in "Steam case, red" is still made lowercase in the code; it is a colour label from the app's own list, and both languages write colour names in lowercase.
- `docs/CHANGELOG.md` gets one line under "Behind the scenes" (nothing changes for people using the window).

Added during the work, each with the owner's answer: the range a slider reads out ("0 (0 to 359)") is one message and its Portuguese says "a" ("0 a 359"); the name of a theme in a sentence comes from its translated label (`theme_label`) and no longer from its internal key. Left as they are, at the owner's word: the Art summary on the Make step (two phrases joined with a comma, first letter made capital in code).

## Not in this spec
Wording changes, new languages, the joins of whole sentences, the comma between two labels in `reasons.py` ("Normal case, No marks"), the separators like " · " and ". " that are not words, and the README.

## Constraints
English and Brazilian Portuguese texts exactly as today (a person comparing before and after sees no change in the window); every message has a Portuguese translation (an existing test checks); the key name still comes from the computer (Cmd+S on macOS, Ctrl+S elsewhere).

## How we will know (the checks)
1. A test reads every QML file and fails if a `qsTr(...)` is glued to something with `+` (before or after it). It fails today for the places above in QML (a separator such as " · " is allowed).
2. A test reads the Portuguese list and fails if a message starts with `,`, `.`, `:`, `;` or `)`, or ends with `,`, `:` or `(` (with or without a space after). It fails today for the pieces `". Change"`, `", locked"`, `", done"` and `"Steam case, "`.
3. Tests that read the built window say the texts are the same as before: the step 1 instruction (English and Portuguese, with the key name in the middle), the case name of a group, and the screen reader names (through the accessibility interface, as the existing tests do).
4. The full test suite passes.
5. A look at the real window on the owner's desktop in both languages: step 1 (the instruction with the key), the Case step (a group's case name). The agent cannot do this one; it says so.
6. The review of rule 12 (`/thermo-nuclear-code-quality-review`, user-only) is run by the owner before the push; the agent fixes every finding first.
