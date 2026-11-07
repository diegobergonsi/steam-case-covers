# Manage a group: design

## Why
Today a group on Home is only a switch that means "also remove this group when I press Reset". The only way to change a group is to go through the Pick games path again. People want to open a group and change it: add or remove games, rename it, delete it. The most common thing will be adding and removing games.

## What the person sees

**Home, Your Groups.** Each group is a row: its name, its case and number of games, and a **Manage** button (at least 44 px tall). The switches are gone. Manage is greyed out while Steam work or Make is running.

**The Manage window.** It opens on top of the app, as an overlay like the app's other boxes (the app has one window). The mock is at https://claude.ai/artifact/CKgsbZCqxEL7DqAmuSjteC (private to Diego).
- Name field with a **Rename** button. A name another group already has (capitals ignored) or a name of 0 or more than 40 letters is refused with a message in plain words.
- Games: the person's library by name, a search box, a tick box per game, the group's games ticked. A game that is in another group shows that group's name; ticking it moves it here (a game is in one group only).
- A line above Save: "Changes show on your covers the next time you make covers, with "Same case" or "Pick games". Nothing on Steam changes until then."
- **Save** applies the changes, then a toast says the same sentence. **Cancel** drops them.
- Unticking every game: a yellow line says "No games ticked. Saving would delete this group." Save then deletes the group (Diego agreed).
- **Delete group** asks "Delete "X"?" first (existing ConfirmDialog, Cancel has the focus).

**Reset.** The "Reset to Steam's default art" question gets a checklist of groups, all unticked. A ticked group is reset and deleted, as the switches do today. Groups not ticked stay.

## Goals
- Add or remove games, rename, delete, all from one window opened from Home.
- Say clearly that nothing changes on the covers until the next make.
- Keep the Reset choice, moved to where it matters.

## Non-goals and anti-goals
- No cover is made inside Manage. It never starts Make, never touches Steam.
- Changing a group's case or colour is not here (the Case step does it).
- The "Your groups" switches on the Make screen stay as they are.
- A game must never end up in two groups, and a group must never be saved with no games.

## Constraints found in the code
- A cover made for a group carries the group id inside the PNG (`GROUP_CHUNK`); the usual flow leaves such covers alone. `engine/steamcase.py: forget_group` removes that note.
- Groups are saved by Make only for games that have a cover. `engine/groups.py` has `assign`, `delete`, `drop_games`; there is no rename yet.
- `qtui/groupticks.py` serves Home and Make; the Make screen still needs it.
- Game names come from Steam's store on a worker thread (`qtui/picker.py`, `RowsModel`). Manage needs its own ticks so it does not change the Pick games choices.
- The app's rules apply: touch size 44 px, durations through `Theme.dur`, Title Case section names, every English string in `i18n_pt_br.py`, README and docs kept in step.

## What is decided and what is left
Decided by Diego:
- The **Manage** button, a window to add/remove games, rename and delete.
- The yellow warning when no games are ticked.
- A removed game only stops being part of the group; its cover stays as it is.
- The person is told the change takes effect on the next make, by "Same case" or "Pick games".
- Option 2: the Reset choice moves into the Reset question.

My calls (check these):
- Manage is an overlay, not an OS window.
- Remove, rename and delete are saved at once on Save (the group list and the cover note). Added games are held until the next "Pick games" make, because their covers do not exist yet and a group may only hold games that have one.
- The notice appears twice: a line before Save and a toast after.

Left to the builder: how the added games are held until the next make (for example ticked and assigned to the group in the Pick games path, or kept next to groups.json); the exact English strings; the Portuguese strings.

## Done means
- Tests first for: rename (valid, taken, too long, same name), set games (add, remove, move from another group, remove all deletes the group), the Reset checklist, and the Manage window (opens, ticks, search, warning, Save, Cancel, Delete asks).
- Whole suite green, also under the one-core stress run.
- README, `docs/ui-guide.md` and the Portuguese README updated; screenshots of Home retaken.
