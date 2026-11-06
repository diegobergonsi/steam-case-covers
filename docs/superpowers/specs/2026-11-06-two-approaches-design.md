# Two approaches, made clear (Home and navigation): design

Date: 2026-11-06. Origin: an Impeccable critique of the whole flow (score 27/40) and a design interview with the owner. This is item 1 of 6 in the UI work plan; the other five are listed at the end and are not part of this spec.

## Problem
The window has two ways to make covers: **automatic** (one case for every game on the list, 5 steps) and **by hand** (pick games, put them in groups, a case per group, 6 steps). Today the owner finds that nothing says there are two approaches. Home offers the second one as a quiet button in the middle of the page, both flows open with the same "1. Game list", and the left menu never says which one you are in.

## Goal
A person understands within seconds that there are two approaches, which one they are in, and how long each is.

## Decisions (all confirmed by the owner)
- Automatic leads: it is the easiest and what most people want. It gets a sky-blue edge and a small tag "Best for most people". Sky blue is the existing "one voice" colour; no new accent.
- Home shows two equal cards (side by side; stacked when the window is narrow). The whole card is the click target. There is no button. A small text cue sits in the card: "Start →", and "Continue →" on the card of the path in progress.
- Titles describe the result, not the style, and do not say "all games" (installed-only is possible):
  - Automatic: "The same case for every game on your list". Line: "Choose a look once. Every game on your list gets it." Steps: "5 steps".
  - By hand: "Pick games, choose their cases". Line: "Put games in groups and give each group its own case." Steps: "6 steps".
- The footer button "Start →" / "Continue →" of Home is removed. Home has no filled button.
- The old "Pick games by hand" section is removed (the card replaces it).
- A returning person keeps the clickable step list, now under the cards, for the current path only, headed "Your progress: <path name>".
- Left menu: a heading under "Home", above the other steps: "Same case · 5 steps" or "Pick games · 6 steps". It shows on every screen, Home included (the menu already lists the steps of the current path there). Step names do not change; "1. Game list" is the same screen in both paths.
- Choosing the other card from Home just switches, with no warning (the game list is shared). While covers are being made or added to Steam the switch is blocked (it already is); the card then says "Wait until this finishes".
- No switch in the middle of a path. Home is the way to change.
- Portuguese uses the feminine "case": "A mesma case para todos os jogos da sua lista", "Escolha os jogos e as cases".

## Calls made by the planner (owner can reverse)
- The nav heading is 24 px high, so the minimum window height grows from 528 to 552 (the Deck is 800).
- The card outline uses the control-edge colour on the card colour (3.5:1), not on a raised fill (2.83:1, below the 3:1 rule).
- Section names on Home: cards `home_section_paths`, progress `home_section_progress`.

## Not in this spec
Undo on Home, Cases layout, end of Apply, touch sizes of other controls, contrast of other controls, copy of other screens. Those are plan items 2 to 6.

## Constraints
640 px minimum width, the Steam Deck's 800 px height, English and Brazilian Portuguese, keyboard (one Tab stop per card, Enter and Space), names for screen readers, nothing that depends on hover, every size from `Theme.qml`, no new colour or font. Refinement: keep the identity of the window.
