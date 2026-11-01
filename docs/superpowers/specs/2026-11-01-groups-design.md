# Groups of covers made by hand: design

Status: approved in conversation on 2026-11-01 (grilling rounds 1 to 4). Builds on `2026-10-31-platform-cases-design.md`.

## Why
A user asked to set the look of specific games by hand, for example gold for 100% games, green for finished games, red for dropped ones. The manual flow ("Pick games by hand") already puts chosen games in a console case. It cannot give chosen games the Steam case in another colour, and it forgets what you chose: the usual flow cannot tell your hand-made covers from the rest.

## What the user gets
1. **Groups.** In the Case step of the manual flow, games are put in a **named group**. The name is filled in from the case ("Xbox 360", "Steam case, red") and can be edited. A group has one case: a console case, or the Steam case in one ready-made colour (the nine swatches of the Look step) or gold.
2. **Saved.** Groups are remembered between runs. The Case step starts with the saved groups ("Add to: Red Steam Cases, 12 games"), then "New group". Adding games to a saved group keeps its case. A game is in one group only: putting it in another group takes it out of the first; an empty group disappears. A group can be deleted: its covers stay but are no longer protected.
3. **Left alone.** The usual flow never repaints covers of a group. Colour, theme, 100% and "other look" checks, and the "mixed colours" check of Apply, ignore them.
4. **Repaint on request.** The Make step of the usual flow and the Reset step list the groups with a tick box each, all unticked. A ticked group is repainted (Make) or removed from Steam (Reset) and then deleted. The confirmation names each ticked group and its game count ("The group 'Red Steam Cases' (12 games) will be repainted and deleted.").
5. **No cheating.** The rosette and ribbon go only on games that are really at 100% on the games page the user loaded, in every case and group. Gold is only a colour. (Unchanged: this is how the 100% step works already.)

## Non-goals
Free colour sliders for a group; the gold border for a group; renaming a group's case (delete and make a new one); per-group family corner; groups for the usual flow; syncing groups between computers.

## Decisions I made (not the user)
- **Where groups live:** one file, `groups.json`, in the covers folder. The user agreed to "per Steam account", but the covers folder is one per user, shared by the accounts, so a file per account would not match what it protects. Groups are keyed by appid, which belongs to one game whatever the account.
- **How a cover knows it is by hand:** a PNG note `steamcase-group` (the group's id) on every cover made in the manual flow, console covers too. All folder checks that skip console covers (`cover_platform(...) is None`) skip any hand-made cover through one helper. The file holds names, cases and members; the notes make protection survive a lost or damaged file.
- **Gold** is the case colour of `GOLD_HUE`; it carries no marks by itself.
- **Marks in a group** are the ribbon or rosette of the run's 100% step on really-completed games only (as for console cases): no gold case or gold border treatments.
- **Covers made by the first version of the manual flow** need no migration: it is not released.

## Failure modes the tests must cover
A groups file that is missing, empty, not JSON, the wrong shape, or has a duplicate or empty name, a name too long, or appids that are not numbers: the app starts with no groups and says so, never crashes, and never deletes covers. A group member whose cover was deleted: dropped silently. A cover with a group note but no group in the file: still protected. A repaint of a group whose games are no longer in the library: those entries are dropped. Two groups of the same colour stay two groups.
