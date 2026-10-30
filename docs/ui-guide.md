# UI guide

The rules every screen of the window follows, so a new feature has a place before it is added. Colours keep the Steam-blue dark look the app has today. Anything that is not here is added here first, then built.

## Layout

A left navigation and one screen on the right. The navigation lists Home, then five steps: 1 Game list, 2 Look, 3 100% games, 4 Make, 5 Add to Steam. Discord (with its icon) and "Check for updates" (always the full words) sit at its bottom. A step unlocks when the one before it is done; finished steps stay open. Home is always open and holds Restore and Reset.

## Eleven rules

1. **One job per screen.** Its title says it in four words or fewer ("Choose the look").
2. **One primary button per screen**, always bottom right. Everything else is quiet.
3. **At most three sections per screen**, each with a heading. A fourth thing means a new screen.
4. **A section holds at most three controls.** More is a list or its own screen. A group that works as one tool (the colour slider, the two tone sliders and the swatches) counts as one control, "the colour picker".
5. **A new feature needs a home before code.** Which screen, which section? If none fits, this guide changes first.
6. **Never hide, group.** Optional things are labelled "(optional)", not folded into a drawer.
7. **Spacing says what belongs together.** Related items 8 px apart, sections 24 px, screen edges 32 px.
8. **Say what is happening.** Long work shows progress with a count. An error says the cause, then the fix.
9. **Keyboard, mouse and touch all work**, and on the Steam Deck's 800 px height the primary button never scrolls out of view.
10. **Motion explains, never decorates.** A "reduce effects" setting (and the OS setting) turns it all off.
11. **Whoever changes the look sees the look.** Every screen whose options change the cover (Look, 100% games, Make) shows the preview beside them. Buttons that reach the same goal (open the page, browse, copy the link) sit in one row.

## Colour

Contrast is measured against the card colour. Body text needs 4.5:1, a control's outline needs 3:1. Colour never carries meaning alone: a locked or finished step also changes its icon.

| Token | Value | Use |
|---|---|---|
| Background | `#11151c` | window |
| Card | `#182433` | sections |
| Raised | `#22344a` | chips, fields |
| Accent | `#66c0f4` | primary button, selection (9.1:1 on the background) |
| Text | `#e6edf3` | 13.3:1 |
| Muted | `#93a7bb` | help text, 6.3:1 |
| Faint | `#7d92a8` | locked items, 4.9:1 |
| Control edge | `#5d7a96` | outlines, off switches, 3.5:1 |
| Done | `#5ba32b` | finished step |
| Warning | `#f0b429` | 8.4:1 |
| Error | `#ff7b72` | 6.2:1 |

Text on the accent button is `#0b141d` (9.2:1).

## Type, spacing, shape

| Role | Size |
|---|---|
| Title (one per screen) | 26 px bold |
| Section heading | 16 px bold |
| Body | 14 px, muted for help text |
| Small (status, hints; never the only way to learn something) | 12 px |

Spacing grid: 4, 8, 12, 16, 24, 32, 48 px. Corner radius: 8 (fields), 14 (cards), full (pills). Elevation: flat (a 1 px outline), card (soft shadow, 4 px down, blur 0.8, opacity 0.45), raised (12 px down, 32 px blur). A disabled control is shown at 60%. A hovered filled button is 15% lighter. The blurred backdrop behind the navigation is dimmed to a brightness of -0.5 and a saturation of 0.4.

## Motion

| Moment | Time | What moves |
|---|---|---|
| Press, hover | 90 to 120 ms | a button scales to 95%, colour eases |
| Navigation highlight, switches | 200 ms, ease-out | the highlight glides to the chosen step |
| Screen change | 260 ms, ease-out | fade plus a 30 px slide from the right |

Never loops, bounces, or anything over 400 ms. With "reduce effects" everything is instant.

## Components

Primary button, quiet button, chip, switch, colour picker, slider, progress bar, navigation item, step badge, card, message, info tip. A new component is added to this list first.
