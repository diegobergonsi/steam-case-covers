# Touch targets of 44 px: design

Date: 2026-11-06. Origin: item 4 of 6 of the UI work plan from the Impeccable critique (score 27/40). The first build of this item skipped the owner's routine (no Impeccable skill, no spec, tests that only read files). The owner stopped it and asked for the process to be applied to the same branch, `feat/touch-44`. This spec covers the whole item, including what was already built.

## Problem
`docs/PRODUCT.md` says touch targets are 44 px or more. The window used 36 for list rows, choice buttons, colour squares and slider knobs, 40 for the menu rows, 32 for switch rows, 36 for buttons, 24 for the "i" and the language flags, and 22 for the switch. On a Steam Deck touchscreen small targets are missed and annoying.

## Goal
Everything a finger taps has a tap area of at least 44 x 44 px, with one size in `Theme.qml`, and the window still looks the same (the drawn shapes stay as they were where a bigger shape would look wrong).

## Decisions

Confirmed by the owner:
- **44 px everywhere** (not 36). `Theme.touchSize` is removed; `Theme.touchMin` (44) is the one size.
- **The shortest window becomes 596 px** (was 552) so the menu keeps all its rows at 44 px. Option A of the mockup. The Deck is 800 px tall, so it has about 200 px to spare. No scrolling menu.

The planner's calls (the owner can change them):
- List rows, choice buttons, colour squares, slider knobs, buttons, on/off switch rows, the menu rows and the links at the bottom of the menu are 44 px (`controlHeight`, `fieldRowHeight`, `navRowHeight`).
- The small "i" circle and the language flags keep their drawn size (24 px circle, 32 x 24 flag) inside a 44 x 44 tap box. The circle is `Theme.infoDot` (24).
- The switch keeps its drawn size (38 x 22). Its whole row is the tap area and is 44 px tall.
- The language flags sit at y = 58 and the menu starts at y = 104 so the 44 px flag boxes touch neither the title (one or two lines) nor the first row.
- `docs/DESIGN.md` is updated (buttons and choice buttons at 44, one line about touch) and so are the changelog and `docs/ui-guide.md`.

## Not in this spec
Contrast (item 5), copy (item 6), colours, fonts, spacing between sections, hover behaviour, the README screenshots. `PRODUCT.md` says its platform is "web"; that is wrong but it is a separate fix (reported, not changed).

## Constraints
640 px minimum width, 800 px height on the Deck, English and Brazilian Portuguese (longer words), keyboard focus ring still visible and still around the drawn shape, screen-reader names unchanged, every size from `Theme.qml`, no new colour or font.

## How we will know (the checks)
1. A test reads the real sizes of the built window: every tapped item is at least 44 x 44 (menu rows, flags, the "i" circle, on/off switch rows, choice buttons, colour squares, slider knobs, buttons).
2. A test at the shortest window checks that the flags box does not overlap the title or the first menu row, and that the last footer link is inside the window.
3. A test at the narrowest window (640 px) checks that the colour squares and choice buttons do not run outside their card.
4. The full test suite passes.
5. A look at the real window on the owner's desktop (the offscreen render does not draw page content): the menu, the Look step, the Cases step, an on/off switch row, an "i" tip. The agent cannot do this one; it says so.
6. The review of rule 12 (`/thermo-nuclear-code-quality-review`, user-only) is run by the owner before the push.
