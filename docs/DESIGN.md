---
name: Steam Case Covers
description: A calm, dark desktop window with a list of steps on the left, that steps back so the game covers are the star.
colors:
  night-ground: "#11151c"
  card-navy: "#182433"
  card-raised: "#22344a"
  control-edge: "#5d7a96"
  text: "#e6edf3"
  text-muted: "#93a7bb"
  text-faint: "#7d92a8"
  sky-blue: "#66c0f4"
  ink-on-blue: "#0b141d"
  done-green: "#5ba32b"
  caution-amber: "#f0b429"
  error-coral: "#ff7b72"
  shadow: "#000000"
typography:
  title:
    fontFamily: "system default"
    fontSize: "26px"
    fontWeight: 700
  section:
    fontFamily: "system default"
    fontSize: "16px"
    fontWeight: 700
  body:
    fontFamily: "system default"
    fontSize: "14px"
    fontWeight: 400
  small:
    fontFamily: "system default"
    fontSize: "12px"
    fontWeight: 400
rounded:
  field: "8px"
  card: "14px"
  pill: "9999px"
spacing:
  related: "8px"
  group: "12px"
  card-inset: "16px"
  section-gap: "24px"
  screen-edge: "32px"
components:
  button-primary:
    backgroundColor: "{colors.sky-blue}"
    textColor: "{colors.ink-on-blue}"
    rounded: "{rounded.pill}"
    height: "36px"
  button-quiet:
    backgroundColor: "transparent"
    textColor: "{colors.text}"
    rounded: "{rounded.pill}"
    height: "36px"
  card:
    backgroundColor: "{colors.card-navy}"
    textColor: "{colors.text}"
    rounded: "{rounded.card}"
    padding: "16px"
  chip:
    backgroundColor: "{colors.card-raised}"
    textColor: "{colors.text}"
    rounded: "{rounded.pill}"
    height: "36px"
---

# Design System: Steam Case Covers

The rules a screen follows are in `docs/ui-guide.md`; every size, colour and time lives in `qtui/qml/Theme.qml`. This file explains the look and why.

## Overview

**Creative North Star: "The Quiet Shelf"**

The window is a dark cabinet. A list of steps stands on the left (Home, then five steps), one screen on the right. The covers, the product's real visual payload, are the only things allowed to be colourful; the interface around them is deep blue-black (#11151c), one step lighter for cards (#182433), with a single sky-blue voice (#66c0f4) for the action that matters now.

Density is relaxed: a screen has one job, at most three sections, and one filled button at the bottom right. Honesty and reassurance live in the copy (backups, undo, what will happen before it happens), not in ornament.

**Key Characteristics:**
- Dark tonal layering with soft shadows under cards.
- One accent (sky blue); green, amber and coral appear only as status.
- Fully rounded buttons and chips, softly rounded cards.
- A preview of the cover beside every choice that changes it.
- Motion explains, never decorates, and "Reduce effects" turns it all off.
- Accessible by construction: visible control edges, a keyboard focus ring, names for screen readers, nothing wider than its card.

## Colors

A Steam-night palette: a blue-black ground, navy cards, one sky-blue action colour, status colours used sparingly. Contrast is measured against the card colour: text 4.5:1, control outlines 3:1.

### Primary
- **Sky Blue** (#66c0f4): the one filled button of a screen, the chosen chip, the progress fill, the switch when on, "i" help. Hover is 15% lighter. Text on it is **Ink on Blue** (#0b141d).

### Neutral
- **Night Ground** (#11151c): window background (the navigation is this colour, a little darker).
- **Card Navy** (#182433): card surface.
- **Card Raised** (#22344a): chips, fields, the current step in the navigation, the empty progress track.
- **Control Edge** (#5d7a96): outlines of controls and the off switch.
- **Text** (#e6edf3): headings, labels, steps you can open.
- **Text Muted** (#93a7bb): instructions and secondary copy.
- **Text Faint** (#7d92a8): steps that cannot be opened yet, small notes such as "(optional)".

### Status
- **Done Green** (#5ba32b): finished step.
- **Caution Amber** (#f0b429): warnings, such as Steam being open.
- **Error Coral** (#ff7b72): errors.
- **Shadow** (#000000): the shadow under cards and the dimmed window behind a question.

### Named Rules
**The One Voice Rule.** Sky blue marks the single action or state that matters right now. If two things on screen are bright blue and neither is progress, one of them is wrong.

**The Covers Are Colorful Rule.** The interface stays in the navy family so the cover thumbnails are the most saturated thing on screen.

**The Colour Is Never Alone Rule.** A finished step also shows a tick, a locked one a padlock; a disabled control is shown at 60%.

## Typography

**Font:** the platform's default UI font, no custom font is bundled. Text stays native, scales with the system and reads well on Windows, macOS and the Deck.

### Hierarchy
- **Title** (bold, 26px): one per screen, four words or fewer.
- **Section** (bold, 16px): the heading of a card and of a question.
- **Body** (14px): instructions and status lines; muted for help text.
- **Small** (12px): hints and notes, never the only way to learn something.

### Named Rules
**The Wider Font Rule.** Windows fonts are wider than Linux ones: labels wrap, buttons may not be wider than their card, and a long text is cut with an ellipsis, never pushed out of the window.

## Layout

The navigation (230px) on the left; the screen on the right with a 32px edge. Sections sit 24px apart, related items 8px apart. A screen's sections scroll when the window is short, its footer never does, so the main button is always in view, also on the Steam Deck's 800px height. The preview sits beside the sections and moves above them when the window is narrow (minimum 640px).

## Elevation & Depth

Three levels: flat (a 1px outline), card (a soft shadow, 4px down) and raised (12px down, a wide blur) for a question that covers the window. Words are never drawn inside a shadow effect: a card on a half pixel would blur them, so a question has its shadow as a separate shape behind a plain card.

## Shapes

Soft and pill-shaped. Cards 14px, fields 8px; buttons, chips and switches are fully rounded; badges and the help icon are circles.

## Motion

Press and hover 90 to 120ms, the navigation highlight and switches 200ms, a screen change 260ms (a fade and a 30px slide). Nothing loops, bounces or lasts over 400ms. With "Reduce effects" (or the system setting) everything is instant.

## Components

- **Buttons:** `PrimaryButton` (the one filled button; `quiet: true` is the outlined look) and `QuietButton`. At least 36px tall, bold text, a ring on keyboard focus.
- **Choices:** `ChoiceChips` (one choice out of a few, arrow keys move it), `SwitchRow`, `Swatch`, `GradientSlider`, `ChoiceSummary` (what earlier steps chose, each leading back to its step).
- **Frame:** `ScreenFrame`, `Section`, `Card`, `ButtonRow`, `PreviewCard` (the sample cover, the old picture stays while the next one loads).
- **Information:** `StatusLine`, `InfoTip`, `ProgressBar`.
- **Navigation:** `NavItem` (a name, a small grey note after it such as "(optional)", a tick or a padlock) and `NavLink` (Discord, Check for updates).
- **Questions:** `ConfirmDialog`, which dims the window, puts the safe button in focus and keeps Tab inside.
- **Cover thumbnails (signature):** the covers just made, in a row under the status on the Make screen. They are the product's output and the only saturated imagery in the window.

## Do's and Don'ts

### Do:
- **Do** keep one sky-blue primary action per screen and everything else quiet.
- **Do** say what will happen before it happens, and what was done after.
- **Do** take every size, colour and duration from `Theme.qml`.
- **Do** keep outlines of enabled controls at 3:1 against the card and show a ring on keyboard focus.
- **Do** keep status colours for status only: green done, amber caution, coral error.

### Don't:
- **Don't** put the Steam logo in the app icon or window chrome; it belongs only inside the covers.
- **Don't** introduce a second accent colour or a custom typeface.
- **Don't** use jargon or hide recovery: backups and undo stay stated up front.
- **Don't** put text inside a shadow effect or place anything on a half pixel.
- **Don't** let the layout depend on a large screen; the Deck's 800px height and a 640px width must still work.
