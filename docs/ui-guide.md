# UI guide

The rules every screen of the window follows, so a new feature has a place before it is added. Colours keep the Steam-blue dark look the app has today. Anything that is not here is added here first, then built.

## Layout

A left navigation and one screen on the right. The navigation lists Home, then a heading that names the way you are on with its number of steps ("Same case · 5 steps" or "Pick games · 6 steps"), then the steps of that way: for the same case, 1. Game list, 2. Look, 3. 100% games (optional), 4. Make, 5. Add to Steam. Home shows the two ways as two equal cards (the same case for every game, or pick games and choose their cases); the whole card is the button, the same case leads with a sky-blue edge, and Home has no filled button. You change way from Home, never in the middle of one. Discord and Ko-fi and "Check for updates" (each with its icon; always the full words) sit at its bottom. A step unlocks when the one before it is done; finished steps stay open. Home is always open. Its Undo card (Restore and Reset) shows only when there is something to undo, or with two or more Steam accounts (the account is chosen in it). After an Apply that worked, the Add step shows one Done card (what was added, the first covers, what to do next, and Undo). What a Restore or a Reset did is said in a toast.

## Eleven rules

1. **One job per screen.** Its title says it in four words or fewer ("Choose the look").
2. **One primary button per screen**, always bottom right. Everything else is quiet. (Home has none: its two cards are the way in. On the Case step the footer button changes its words to the action of the moment: "Use this case for 3 games" while a case and games are ready, "Next →" otherwise.)
3. **At most three sections per screen**, each with a heading. A fourth thing means a new screen.
4. **A section holds at most three controls.** More is a list or its own screen. A group that works as one tool (the colour slider, the two tone sliders and the swatches) counts as one control, "the colour picker". **One exception:** the "Add games to a group" section of the Case step holds the group cards, the colours, the name, "Pick more games" and "Delete this group" (up to five). They are one job, putting games in a group, and the section stays together so the page does not jump.
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

Spacing grid: 4, 8, 12, 16, 24, 32, 48 px. Corner radius: 8 (fields), 14 (cards), full (pills). Elevation: flat (a 1 px outline), card (soft shadow, 4 px down, blur 0.8, opacity 0.45), raised (12 px down, 32 px blur). A disabled control is shown at 60%. A hovered filled button is 15% lighter. The navigation panel is the background colour, darkened a little. There is no picture behind the window: every surface is plain.

## Motion

| Moment | Time | What moves |
|---|---|---|
| Press, hover | 90 to 120 ms | a button scales to 95%, colour eases |
| Navigation highlight, switches | 200 ms, ease-out | the highlight glides to the chosen step |
| Screen change | 260 ms, ease-out | fade plus a 30 px slide from the right |

Never loops, bounces, or anything over 400 ms. With "reduce effects" everything is instant.

## Components

Every piece of a screen is one of these, in `qtui/qml/`. A new component is added to this list first (rule 5), and every size, colour and time in it comes from `Theme`.

- Buttons: `PrimaryButton` (the one filled button of a screen; `quiet: true` is the outlined look) and `QuietButton` (the quiet look).
- Frame of a screen: `ScreenFrame` (title, subtitle, sections that scroll with a scroll bar and a bottom fade while there is more below, a footer that never scrolls away), `ScrollCue` (the scroll bar every scrolling page and list uses: always on while there is more to scroll to), `Section` (a card with a heading and an optional note at its right), `Card`, `ButtonRow` (buttons with one goal in one row, wrapping when narrow).
- Cover pictures: `CoverThumbs` (a row of small pictures of the first covers of a run, wrapping when the window is narrow; the Make and Add screens use it).
- Preview layout: `PreviewLayout` (the screens that show a sample cover, Look, 100% games, Case and Make, put their sections inside it: the preview sits at the left with the sections beside it, or above them when the window is narrow; anything under the preview, such as a caption, goes in `underPreview`).
- Navigation: `LanguageFlag` (a small flag under the name of the app that chooses the language; the one in use has a ring), `NavLink` (a quiet link at the bottom of the navigation, with an optional icon: Discord, Ko-fi, Check for updates), `NavItem` (a name, an optional small hint under it such as "(optional)", and a mark when done).
- Ways: `PathCard` (one of the two ways to make covers on Home: title, line, number of steps and a "Start" or "Continue" cue; the whole card is the button, the leading one has a sky-blue edge and a tag, the other the control-edge outline).
- Groups: `GroupCard` (a saved group of covers as a small selectable card of the Case step: the name the person gave it, bold, and under it, small and muted, its case and its games; one choice out of several, the chosen card has the sky-blue edge, at least 44 px tall).
- Choices: `SwitchRow` (a switch with a label that wraps and an optional info tip), `ChoiceChips` (one choice out of a few, arrow keys move it; `groupName` names it for screen readers; `enabled: false` greys it, makes it inert and keeps the choice visible), `Swatch` (a ready-made colour, arrow keys move between them), `GradientSlider` (a slider whose track shows what it does; a swipe with a finger scrolls, a tap or the handle moves it).
- Information: `Toast` (a short message above the footer line that goes away by itself, after 4 seconds plus 50 ms for each character (12 at most) and is read out by screen readers; the shell sends it with its `toast` signal), `StatusLine` (what is happening), `InfoTip` (the small "i"), `PreviewCard` (the sample cover with a soft shadow; the old picture stays while the next one loads), `ProgressBar` (how far a long job is, 0 to 1; the count goes in a `StatusLine` beside it), `ChoiceSummary` (what earlier steps chose, as chips that lead back to their step; the whole group is one control).
- Questions: `ConfirmDialog` (covers the window; a question that must be answered before anything changes. It has its own filled button, the confirm; the safe button, Cancel, has the focus; Escape declines; Tab stays inside; an optional third button sits between them for a second way forward, and an information box shows only OK).
