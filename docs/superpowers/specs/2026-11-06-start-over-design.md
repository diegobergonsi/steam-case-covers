# Start over: a button on Home that puts the window back to its starting point

Approved by the user in chat on 2026-11-06.

## Why
After a half-walked path, a wrong game list or old choices, the user wants one button that makes the window behave as if it had just been opened, without losing anything saved.

## What it does
- A section "Start over" at the bottom of Home, always visible: one muted line ("Restart the app back to its initial settings. Your saved cases, covers and groups are not changed.") and one quiet button, "Start over".
- The button opens the app's own "Are you sure?" dialog (Cancel has the focus). It says what is cleared and what is kept.
- On confirm the window goes back to what a fresh start shows:
  - the way and the steps: the step-by-step way, nothing done, Home shown
  - the chosen game list and the note of its path on disk (`library.txt`), "only installed games" off, the ticked games and the search
  - the colour, theme, marks and 100% page of the Look steps, and "My own case" off
  - the cases given to games but not yet made, and the group being edited (saved groups are read again from disk)
  - the covers made in this run (the list Apply adds), and the result of the last Apply
  - the preview pictures kept in memory, and the downloads folder watchers (a file already in Downloads is not picked up again)
  - the five switches, back to their defaults
- A toast: "Everything was reset to the starting point. Your saved cases, covers and groups were not changed."

## What it never does
Delete or change saved groups, cover files, the user's own case file, Steam files, or the language.
It is off while covers are being made or added to Steam (same rule as switching ways).

## Calls I made
- The name "Start over" (Home already has "Reset to Steam's default art", so "Reset" would be confusing).
- Language is kept.
- No cache folder exists on disk; "cache" means the in-memory preview pictures and the watchers.
