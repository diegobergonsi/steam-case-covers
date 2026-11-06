# The Cases screen, clearer: design

Date: 2026-11-06. Origin: item 2 of 6 of the UI work plan that came out of an Impeccable critique of the whole window (score 27/40), and a design interview with the owner (mockup: the owner saw and approved it). Item 1 (two ways on Home) is merged as PR #47.

## Problem
The Case step of picking games by hand (`qtui/qml/CasesScreen.qml`) breaks the UI guide: five sections, two filled buttons ("Use this case for N games" in section 4 and "Next →" in the footer), the button that does the work sits below the fold on a short screen, the "Name your group" section appears after a pick and makes the page jump, there is no preview (rule 11), and "Delete group" deletes at once.

## Goal
The person picks a case, sees what it looks like, names or chooses a group, and gives the games the case with one obvious button that never scrolls away.

## Decisions (all confirmed by the owner)
- **Three sections**, no numbers in the headings (the menu already numbers the step "3. Case"): "Choose a case"; "Add %n games to a group" ("Add games to a group" with 0 ticked games); "Options".
- **A preview** (`PreviewCard`) beside the sections: the chosen case with a sample game. With no case chosen it shows the case most games are in, else the Steam case (planner's call). Limit: the Steam case preview is the default blue; it does not follow the colour picked (the existing preview address has no colour).
- **The footer has the only filled button.** It reads "Use this case for %n game|%n games" (or "Add %n game to %1|…" for a saved group) only when a case is chosen **and** games are ticked; otherwise "Next →", enabled once some games have a case. A case picked with no games ticked never blocks "Next".
- **Group cards** replace the pill buttons: one small selectable card per saved group, two lines. Line 1: the name the person gave it, bold, one line, cut with "…". Line 2: the case and the number of games, small and muted ("PlayStation 5 · 3 games"). A chosen card has the sky-blue edge, the others the quiet edge. At least 44 px tall. A "New group" card comes first in the same style; its second line is the case picked, or "Pick a case above".
- **No saved groups:** the saved-group part of the row is greyed with "You don't have any groups yet." ("New group" stays).
- **Case and group are both clickable at any time.** Clicking a case picture means a new group and un-selects a saved group; a **toast** says "You picked a new case, so the saved group was unselected." Clicking a saved group's card highlights its case and shows its name, not editable, and hides the colours.
- **Toast** (new component `Toast.qml`, window level): a small message above the footer, shown for 4 seconds, faded in and out (instant with "Reduce effects"), announced to screen readers. It goes into `docs/ui-guide.md` first. Shell has a signal `toast(str)`.
- **Delete this group:** a quiet button in section 2, shown when a saved group is chosen. It asks first (ConfirmDialog): "Delete the group “%1”? Its games lose this case here. Covers already on Steam stay until you Reset or make covers again." Cancel has the focus.
- **"So far"** line in section 2: "So far: PlayStation 5 · 3 games, Xbox One · 1 game" (empty until something is assigned), and a quiet "Pick more games" button under it, always visible.
- The note about "My own case" and its error stay under the case pictures. The name field keeps today's behaviour (pre-filled with the case's name, editable).
- Portuguese uses the feminine "case". Strings: see the plan.

## Not in this spec
Home, Look, Make, Apply, how groups are saved, the Home "Your groups" list. Items 3 to 6 of the work plan.

## Constraints
640 px minimum width, 800 px height on the Deck, English and Brazilian Portuguese, keyboard (group cards and case pictures are one Tab stop each, Enter and Space), screen-reader names, no hover-only behaviour, touch targets of 44 px or more for new controls, every size from `Theme.qml`, no new colour or font. Refinement: keep the identity of the window.
