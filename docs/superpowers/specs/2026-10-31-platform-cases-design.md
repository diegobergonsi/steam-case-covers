# Design: pick games by hand, and put them in console cases

> **Later change (2026-11-01):** the final frames were hand-made, so `tools/build_cases.py` and its logo files are gone; `cases.json` is written from the frames by `tools/measure_cases.py` and has only `window` and `overlay` (no `marks_dy` or `corner`). On every case the rosette is at the left under the banner, the family corner at the top right, and the ribbon is 482 px wide. Read the sections below as the history of the design.


Date: 2026-10-31. Status: draft for the user's approval. Nothing is built.

## Intent and why

People want the library to look like a shelf of real game boxes, and a game's real box depends on where it came from: The Last of Us is a PlayStation game, so its cover should sit in a PS5 or PS4 case, not a Steam case. The app cannot know where a game came from, so the person tells it, game by game.

Today the window makes covers for every game in the list, all in the Steam case. The command line can already limit a run (`--only APPID...`), but the window has no way to pick games, and there is only one case design.

## What gets built

1. **A second way through the window, the manual flow**, reachable from Home next to the natural flow. The natural flow (Game list, Look, 100% games, Make, Add to Steam) stays exactly as it is.
2. **Step "Games"**: the games from the loaded game list, a search box (by name), a scrolling list with a tick box per game, a count of how many are ticked, Select all and Clear.
3. **Step "Case"**: a grid showing the real case of each platform, drawn as it will look with the art window in it. The person picks one case for the games ticked in step 1. Going back to Games to pick more games for another case is possible but never required.
4. **Options** (off by default): "Highlight my 100% games" (rosette and ribbon only) and "Mark family games" (the green corner). If off, the cover is just the case.
5. **The manual flow ends like the natural flow**: Make, then Add to Steam (same screens, same backup and Restore behaviour).
6. **New cases** (original drawings, exact copies of the physical cases, real console logos): PS3, PS4, PS5, Xbox 360, Xbox One, Xbox Series X|S, Switch, Switch 2. The Steam case stays as the ninth choice. Games the person never picks keep the Steam case.

## Decisions by the user

- Cases are exact copies of the real ones; **no customisation** on them: no colour, no brightness, no theme, no gold case, no gold border.
- Every case fills the 600x900 tile that Steam uses for portrait art, like the Steam case today, even where the physical case has another shape.
- **Real logos** (PlayStation, Xbox, Nintendo), knowing they are trademarks in a public repo and could draw a takedown request.
- The 100% highlight and the family corner are available on platform cases **as opt-in options**.
- Repeating the pick for another group is optional, not forced.
- The platform list above is the first version.

## Goals, non-goals, anti-goals

Goals: a person can give chosen games a console case in a few clicks; the result is applied to Steam like any other cover; Restore and Reset keep working.

Non-goals: guessing the platform; colour, tone or theme on platform cases; gold marks on platform cases; more platforms in this version; changing the natural flow; splitting `steamcase.py` (skipped on 2026-10-31).

Anti-goals: covers made before this feature must keep being recognised exactly as now (`assets/frame.png` is never regenerated); a platform cover must never be mistaken for the user's own art, and the user's own art must never be mistaken for a platform cover; the natural flow must never silently overwrite or remove a platform cover.

## Constraints

- Covers are 600x900 PNG (`SIZE`), art window per case to be defined; the art is scaled to cover the window and centre-cropped, as now.
- Cases are drawn by a maintainers' script (like `tools/build_frame.py`) from SVG sources, and committed under `assets/`; the packaged app needs them in `steamcase-qt.spec` (`ASSETS`).
- The window is Qt (`qtui/`); new screens follow `docs/ui-guide.md` and the step logic in `qtui/steps.py`. The engine stays `steamcase.py`.
- Logos: sourced as vector files with a licence recorded in `docs/THIRD_PARTY.md`, with a trademark notice (the marks belong to their owners; this project is not affiliated). The user reads that text once, it is not legal advice.
- Public text (README, changelog, PR) must not mention Flatpak, Flathub or AUR (house rule).

## Calls I made (the user can overrule them)

1. **The cover file says which case it has.** A PNG note (like `steamcase-tone` and `steamcase-done` today) names the platform. The file is the single source of truth: no separate list of "game X has case Y" to keep in sync. Reset and Restore recognise a platform cover by that note plus a pixel check of the case, as they do for Steam covers.
2. **The natural flow leaves platform covers alone.** Make in the natural flow does not rebuild a game that already has a platform case, and "other colour / other theme" questions ignore them. Apply's refusal of a folder with covers in more than one colour or theme (`mixed_cover_colours`, `mixed_cover_themes`) must not fire because of platform covers.
3. **Opt-in options are only the rosette-and-ribbon marks and the family corner**, placed to avoid each case's logo band.
4. **The manual flow only makes the covers of the ticked games**, using the existing `only` parameter of `make_covers`.
5. **Choices are kept for the session only**; nothing new is saved to the settings file.
6. **The manual flow needs a game list.** If none is loaded (and "Only my installed games" is off), it starts with the same Game list step as the natural flow, and a list loaded in either flow serves both.
7. **Reset** removes platform covers too (they are ours), through the same backup.

## Left to the builder

The drawings and their art windows; the exact file layout and names; how the screens look inside the approved flow (mockups agreed in the conversation: Games list with search and tick boxes, Case grid with the real overlays); test strategy (tests first, as always; a pixel test per case); where the PNG note and the recognition code live; the order of work.

## Open risks

- Real logos can lead to a takedown request (accepted by the user).
- I do not have the real case artwork; each case is drawn from public references, and "exact" will be judged by the user on screen.
- The shape of a real Switch case is much narrower than the tile; stretched to 2:3 it will look different from the physical one (accepted by the user).
