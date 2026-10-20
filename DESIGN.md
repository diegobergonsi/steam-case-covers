---
name: Steam Case Covers
description: A calm, dark, three-step desktop window that steps back so the game covers are the star.
colors:
  night-ground: "#11151c"
  card-navy: "#182433"
  card-raised: "#22344a"
  hairline: "#2c4259"
  control-edge: "#5d7a96"
  text: "#e6edf3"
  text-muted: "#93a7bb"
  text-faint: "#7d92a8"
  sky-blue: "#66c0f4"
  sky-blue-hover: "#8fd3ff"
  sky-blue-pressed: "#45a5dc"
  ink-on-blue: "#0b141d"
  done-green: "#5ba32b"
  caution-amber: "#f0b429"
  error-coral: "#ff7b72"
  focus-ring: "#ffffff"
  raised-hover: "#2b405a"
  disabled-fill: "#26384b"
  disabled-edge: "#223244"
  disabled-track-on: "#2a5a78"
  disabled-knob: "#8a9bab"
  progress-track: "#0c1219"
  progress-edge: "#1f2e3f"
  tooltip-ground: "#0b1017"
typography:
  title:
    fontFamily: "system default (Tk default font)"
    fontSize: "22pt"
    fontWeight: 700
  headline:
    fontFamily: "system default (Tk default font)"
    fontSize: "15pt"
    fontWeight: 700
  card-title:
    fontFamily: "system default (Tk default font)"
    fontSize: "14pt"
    fontWeight: 700
  body:
    fontFamily: "system default (Tk default font)"
    fontSize: "11pt"
    fontWeight: 400
  label:
    fontFamily: "system default (Tk default font)"
    fontSize: "11pt"
    fontWeight: 700
rounded:
  card: "18px"
  pill: "9999px"
spacing:
  page-gutter: "28px"
  card-gap: "14px"
  card-inset-x: "22px"
  card-inset-y: "18px"
  row-gap: "8px"
components:
  button-primary:
    backgroundColor: "{colors.sky-blue}"
    textColor: "{colors.ink-on-blue}"
    rounded: "{rounded.pill}"
    height: "46px"
  button-primary-hover:
    backgroundColor: "{colors.sky-blue-hover}"
  button-primary-pressed:
    backgroundColor: "{colors.sky-blue-pressed}"
  button-quiet:
    backgroundColor: "{colors.card-raised}"
    textColor: "{colors.text}"
    rounded: "{rounded.pill}"
    height: "46px"
  card:
    backgroundColor: "{colors.card-navy}"
    textColor: "{colors.text}"
    rounded: "{rounded.card}"
    padding: "18px 22px"
---

# Design System: Steam Case Covers

## Overview

**Creative North Star: "The Quiet Shelf"**

The window is a dark cabinet that holds three labelled stations and gets out of the way. The covers, the product's real visual payload, are the only things allowed to be colorful; the interface around them is deep blue-black, one step lighter for cards, with a single sky-blue voice for the action that matters now. It should feel at home next to Steam without copying the Steam client, and stay calm enough that a non-technical user never wonders what to click.

Density is relaxed and linear: three cards stacked in reading order, each with a numbered badge, a plain-English instruction, and its controls. Nothing decorative, no illustration inside the window, no motion beyond state changes. Honesty and reassurance live in the copy (backups, undo), not in ornament.

**Key Characteristics:**
- Dark tonal layering, no shadows.
- One accent (sky blue); green, amber and coral appear only as status.
- Fully rounded controls, softly rounded cards.
- Text-forward: every card opens with a sentence of instruction.
- Accessible by construction: visible control edges, white keyboard focus ring, scroll fallback on small screens.

## Colors

A Steam-night palette: a blue-black ground, navy cards, one sky-blue action color, and status colors used sparingly.

### Primary
- **Sky Blue** (#66c0f4): the current primary action, the active step badge, progress fill, and the "i" help badge. Hover **Sky Blue Lifted** (#8fd3ff), pressed **Sky Blue Deep** (#45a5dc). Text on it is **Ink on Blue** (#0b141d).

### Neutral
- **Night Ground** (#11151c): window background.
- **Card Navy** (#182433): card surface.
- **Card Raised** (#22344a): quiet buttons and the off-state of raised controls.
- **Hairline** (#2c4259): card outline and pressed quiet buttons.
- **Control Edge** (#5d7a96): outline of controls and off switches, 3:1 against the card so a control is visible without its label.
- **Text** (#e6edf3): headings, labels, primary copy.
- **Text Muted** (#93a7bb): instructions and secondary copy.
- **Text Faint** (#7d92a8): locked steps and hints; kept at 4.5:1 on the card because it carries real text.

### Status
- **Done Green** (#5ba32b): completed step badge.
- **Caution Amber** (#f0b429): warnings, such as Steam still running.
- **Error Coral** (#ff7b72): errors.
- **Focus White** (#ffffff): keyboard focus ring, switch knob and done-badge tick.

### Control states
- **Raised Hover** (#2b405a): hover fill of an outlined button.
- **Disabled Fill / Edge** (#26384b / #223244), **Disabled Track On** (#2a5a78), **Disabled Knob** (#8a9bab): disabled controls stay visible but clearly unavailable; exempt from the 3:1 edge rule.
- **Progress Track / Edge** (#0c1219 / #1f2e3f): empty bar; the fill and the status text carry the value.
- **Tooltip Ground** (#0b1017): help bubble background.

### Named Rules
**The One Voice Rule.** Sky blue marks the single action or state that matters right now. If two things on screen are bright blue and neither is progress, one of them is wrong.

**The Covers Are Colorful Rule.** The interface stays in the navy family so the cover thumbnails are the most saturated thing on screen.

## Typography

**Font:** the platform default UI font (Tk default font), at 11 pt base. No custom font is bundled for the window. This keeps text native, scalable with OS font settings, and legible on Windows, macOS and the Deck.

**Character:** plain and native; hierarchy comes from size and weight, not from a typeface.

### Hierarchy
- **Title** (bold, 22pt): the app name in the header.
- **Headline** (bold, 15pt): dialog titles.
- **Card title** (bold, 14pt): each step's name.
- **Body** (regular, 11pt): instructions, status lines; wraps at about 620px (scaled).
- **Label** (bold, 11pt): button text and warning lines.

### Named Rules
**The Scale With The System Rule.** Layout measures are derived from the real font line height and screen DPI (`px()`), never fixed pixels. Text must never clip when the desktop scales fonts.

## Layout

A single vertical column inside a scroll frame, with a 28px gutter and 14px between cards (7px above and below each). A header (icon, title, one-line tagline, a quiet "Check for updates") sits above three cards in fixed order. The scrollbar appears only when content does not fit, so the Steam Deck's 800px-high screen and small windows keep every control reachable by mouse wheel or Tab. The window is fluid down to about 520px wide (scaled): text wraps to the card width, button rows wrap onto a second line (the `Flow` widget), and the header's update button drops under the title. Touch drag on the content scrolls it. All measures go through the DPI-aware `px()` helper. Inside a card: instruction text first, then a row of buttons, then switches, then a status line; rows are separated by about 4 to 8px.

## Elevation & Depth

Flat. Depth is conveyed only by tonal layering: ground, then card (one step lighter) with a 1px hairline edge, then raised quiet controls. There are no shadows. State changes (hover, pressed, locked) are color shifts; locked steps drop to faint text and a dimmed outline.

### Named Rules
**The Flat-By-Default Rule.** No drop shadows, glows, or gradients in the window. Hierarchy comes from tone and hairlines.

## Shapes

Soft and pill-shaped. Cards use an 18px radius with a hairline outline. Buttons, switches, the progress bar and the focus ring are fully rounded (radius = half height). Badges and the help icon are circles. Everything is drawn on Canvas with `round_rect`, so corners stay crisp at any DPI.

## Components

### Buttons
- **Shape:** fully rounded pill, at least 46px tall (scaled), text bold.
- **Primary:** Sky Blue fill, Ink on Blue text. Hover lifts to #8fd3ff, press deepens to #45a5dc.
- **Outlined:** Card Raised fill with Control Edge outline and Text color; hover Raised Hover, pressed Hairline.
- **Quiet (text-only, by design):** no fill and no outline at rest, Text Muted label (6.3:1 on the card); hover fills Card Raised and lifts the label to Text, pressed Hairline. For rare or secondary actions (Browse…, Copy link, Check for updates, Reset) that must not compete with the primary.
- **Disabled:** Card fill, faint outline and faint text, so it reads as present but unavailable (for example Cancel).
- **Focus:** a 2px white ring outside the pill.

### Switches
- Pill track (Sky Blue when on, Control Edge when off, 3.5:1 on the card), round knob (white on, #8a9bab off), the label to the right. Same white focus ring.

### Cards
- 18px radius, Card Navy fill, Hairline outline, 22px by 18px inner padding. The body grows with its content. A step badge and bold title open each card.

### Step badge
- A circle: Done Green with a white tick when complete, Sky Blue with the number when current, faint outline with a faint number when locked.

### Progress bar
- Pill track (#0c1219, outline #1f2e3f), Sky Blue fill.

### Info badge and tooltip
- A small Sky Blue circle with "i"; the tooltip is a dark panel (#0b1017) with 12px by 10px padding, wraps at 360px.

### Dialogs
- Card-styled modal with a leading circular icon (warning amber, question, info), a 15pt bold title, 11pt body with muted and warning styles.

### Cover thumbnails (signature)
- The generated covers shown in a row at the end of "Make the covers", about 76px wide, left-aligned. They are the product's output and the only saturated imagery in the window.

## Do's and Don'ts

### Do:
- **Do** keep one sky-blue primary action visible per card and use outlined or quiet buttons for everything else.
- **Do** put a plain-English sentence above the controls in every card, in Text Muted.
- **Do** route every measure through `px()` and the real font line height.
- **Do** keep outlines and switch tracks of enabled controls at 3:1 against the card (Control Edge) and show a white ring on keyboard focus. Quiet text buttons are the one deliberate exception.
- **Do** keep status colors for status only: green done, amber caution, coral error.

### Don't:
- **Don't** add shadows, gradients, glows or decorative illustration to the window.
- **Don't** put the Steam logo in the app icon or window chrome; it belongs only inside the covers.
- **Don't** introduce a second accent color or a custom typeface.
- **Don't** use jargon or hide recovery: backups and undo stay stated up front.
- **Don't** fix pixel sizes or let the layout depend on a large screen; the Deck's 800px height must still work.
