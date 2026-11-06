# Contrast, to the recommended accessibility rule: design

Date: 2026-11-06. Origin: item 5 of 6 of the UI work plan from the Impeccable critique (score 27/40), and a short interview with the owner who has strong vision problems and said not to take their eyes as the measure: apply the recommended guideline. A mockup of three options helped them decide. Items 1 to 4 are merged (#47 to #51).

## Problem
`docs/ui-guide.md` promises that text has 4.5 to 1 contrast and outlines 3 to 1, but it measures only against the card colour. Three colours sit on the lighter navy fill ("raised": the open step in the menu, the help bubble, a row under the mouse, the main button when switched off) and miss the rule there:

| Colour | Used for | On the raised fill now | Rule |
|---|---|---|---|
| Faint grey `#7d92a8` | locked steps, small notes | 3.95 | 4.5 |
| Done green `#5ba32b` | finished step, the "done" line | 4.05 | 4.5 |
| Control edge `#5d7a96` | outlines of the help bubble and of tick boxes, the off switch, the scroll bar | 2.83 | 3 |

## Goal
Every colour meets the rule on every fill it is really drawn on, and a test says so for all of them, not only for the card.

## Decisions

Confirmed by the owner:
- **Follow the recommended rule (WCAG 2.2 level AA):** text 4.5 to 1, outlines and control shapes 3 to 1. Option A of the mockup.
- **The grey subtitles and help text stay as they are** (muted `#93a7bb`: 7.4 on the window, 6.3 on a card, 5.1 on the raised fill; they already pass). The owner said these are the hardest for them to read; they chose to follow the rule and not to go beyond it. Brighter subtitles (7 to 1) stay a possible later change.

The planner's calls (the owner can change them):
- Faint grey becomes `#8a9db1` (4.55 on raised), done green `#6aab3e` (4.53), control edge `#637f9a` (3.04). They are the dimmest colours that pass, so the look changes as little as possible.
- Where each colour is measured: faint, done, error, warning and the blue accent on the window, the menu panel, the card and the raised fill; control edge on the same four; muted and white text also on the raised fill while the mouse is over it (it is a little lighter then). Faint, done and edge are not measured on that hovered fill because they are not drawn there.
- A control that is switched off is shown at 60% and the rule does not apply to it (WCAG leaves it out).
- The dark text on the blue main button, also under the mouse, is measured as well (9.2 and higher).
- `docs/ui-guide.md` (colour table and the sentence about the card) and `docs/DESIGN.md` (colour names and values, the contrast sentence) are updated to the new values and to "measured on every fill".

## Not in this spec
Brighter subtitles, copy and wording (item 6), the size or weight of text, the colour of the focus ring (it is white on the window, 13 to 1 and better), any new colour, hover and press effects, the README screenshots.

## Constraints
No new colour name or font; every colour stays in `qtui/qml/Theme.qml`; the colours of `docs/ui-guide.md`, `docs/DESIGN.md` and `Theme.qml` stay equal (a test checks it); English and Portuguese unchanged; the look of the window stays calm (the three colours move a little, nothing else).

## How we will know (the checks)
1. A test lists the pairs above (every text colour on every fill it is drawn on, outlines against their fills, dark text on the blue and green buttons) and checks the numbers from the colours in `Theme.qml`. It fails today for the three colours above (checked against the current `Theme.qml` before the change).
2. The test of the colour table (`Theme.qml` equals the guide) passes with the new values, and a second check reads `docs/DESIGN.md` for the same values.
3. The full test suite passes.
4. A look at the real window on the owner's desktop: the menu with a locked step, a text field with its placeholder, the Look step (choice buttons, switches, the off switch outline), the end of Apply (green line). The agent cannot do this one; it says so.
5. The review of rule 12 (`/thermo-nuclear-code-quality-review`, user-only) is run by the owner before the push; the agent fixes every finding first.
