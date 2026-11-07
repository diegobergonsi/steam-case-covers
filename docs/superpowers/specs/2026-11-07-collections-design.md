# Steam collections on "Pick your games": one click ticks a whole collection

Approved by the user in chat on 2026-11-07. The idea comes from a user of the app, who sent a mockup (a row of collection buttons above "Your games").

## Why
Many players already sorted their library into Steam collections (Completed, Backlog, Playing…). On "Pick your games" they would tick each game one by one. One click on a collection should tick all its games.

## What it does
- On the Games screen, in the "Find games" section, below the search box, a row **"Your collections"** with one pill button per collection: the collection's name as Steam shows it (emoji included) and the number of games it would tick, for example `Completed 💯 (378)`.
- Which collections: the normal ones, a plain list of games. This includes Steam's own **Favorites** and **Hidden**. Not shown: dynamic collections (rule-based ones that hold a filter instead of a list; the app cannot work out their games), and a collection with 0 games in the current list. The README says dynamic collections are not supported.
- The count is the number of games of the collection that are in the list on screen (the game list file, or the installed games). Games of the collection that are not in that list are ignored. Steam's own sidebar number may be different.
- **First click, nothing ticked:** the collection's games get ticked.
- **Click while any game is ticked** (by hand, by "Select all shown" or by an earlier collection): a pop-up with three buttons.
  - **Add them** (the filled, main button): tick the collection's games too. The ticks already there stay.
  - **Replace them:** untick everything, then tick the collection's games.
  - **Cancel** (has the focus, Escape does the same): nothing changes.
  - The pop-up says how many games are ticked now and how many the collection has; each choice says what it does and the total it gives (for example "124 in total").
- If every game of the collection is already ticked and nothing else is, the click changes nothing (no pop-up).
- The buttons only tick. The player can still untick single games, use "Clear" or "Select all shown".
- **Many collections:** the first two rows of buttons show, and a link "Show all 25 collections" opens the rest (and then "Show fewer"). With few collections there is no link.
- **No collections** (no Steam file, no account, an unreadable or odd file, or only dynamic ones): the "Your collections" row is not there at all. No error message. The rest of the screen works as before.
- It works in both ways of getting the list (game list file and "Only my installed games").

## Where the data is
`<Steam>/userdata/<account>/config/cloudstorage/cloud-storage-namespace-1.json`, a local file Steam keeps. It is a list of `[key, entry]`. A key starting with `user-collections.` and an entry that is not deleted (`is_deleted` not true) holds in `value` a JSON text with `name`, `added` (a list of app ids) and `removed`. A collection with a `filterSpec` is dynamic. The members are `added` minus `removed`. The file is only read, never written, and it is read once when the list of games loads (Steam can be running). Verified on the user's own machine (read-only): collections "Favorites" (4), "Hidden" (396), "100% Games" (32), "DEMO SCC" (28) are plain lists; "SIM" and "Action/Adventure RPG" are dynamic with an empty list.

Names and counts come from Steam's file, so they can be anything the player typed; they are shown as plain text, never as markup.

## How it fits the code (answers from the builder check)
- Ids: the games on the screen are numeric Steam app ids (owned apps from the game list file, or installed games from the app manifests), the same ids the collections hold. Non-Steam shortcuts are not in the list and so are never counted.
- "Ticked" means the whole selection in `Picker` (`_selected`), including games the search is hiding. A collection click ignores the search box. ("Select all shown" still ticks only the rows shown.) The pop-up totals and the "nothing changes" rule use the whole selection.
- When the game list changes (another file, installed-only switched), `Picker` already clears the ticks and reloads; the collections are read again in the same load.
- The account: the one chosen on the Apply screen if the player chose one, else the one the app picks first (`pick_account`, the same way Apply works it out). The file is read again each time the Games screen opens, so a later choice of account is followed. If the account is not the one the browser was logged in to, the only effect is which games get ticked; the player sees them ticked and can change them.

## Parts it uses (do not invent new ones)
- A new function in `engine/` that reads the collections of an account (pure, easy to test with a fake file).
- `qtui/picker.py` keeps the collections next to the games, gives them to the screen, and ticks (add or replace) through one new method; the selection logic stays in `Picker`.
- `ConfirmDialog` already has a confirm button, a Cancel and a third button in between (`alternateText`): use it for Add, Replace and Cancel.
- `ChoiceChips`/the pill look of the app for the buttons, `QuietButton` size rules (44 px touch targets), `Theme` colours. The look follows `docs/ui-guide.md` (contrast WCAG AA on every fill, a section holds at most three controls: search, the collections row, the buttons row).
- Messages are whole sentences with `%1`/`%n` blanks (ui-guide rule from #53), in English and Brazilian Portuguese.

## Goals
- One click for a whole collection, safe: the player never loses ticks by surprise.
- Nothing new to learn: the same screen, one extra row.

## Non-goals
- Dynamic collections (a README line says so).
- Writing to Steam's collections (the app never changes them).
- A collection picker on other screens, or remembering which collection was clicked.
- Choosing the collection's account: see "Calls I made".

## Anti-goals (a failure even if it works)
- A button that ticks 0 games or the wrong games.
- An error box or a crash because Steam's file looks different on someone's computer.
- Text on the pop-up or the buttons that is hard to read (the app's contrast rule applies to every fill).

## Calls I made (the user can change these)
- The account: see "How it fits the code". There is no account picker before the Games step, so on a computer with several Steam accounts the collections come from the Apply choice or the most recent account.
- The pop-up wording (draft, in the mockup) and "Add them" as the filled button because it loses nothing.
- Order of the buttons: the most games first, then by name (like the user's mockup). Collections with the same name stay separate buttons. A collection with an empty or missing name is skipped.
- Two rows before "Show all" is measured from the layout, not a fixed number of buttons: the link shows only when the buttons do not fit in two rows, so a resize follows. While collapsed, the buttons in the hidden rows cannot be reached with Tab or a screen reader (they are not visible, not just clipped).
- No pop-up when the click would change nothing.
- Start over clears nothing extra: collections are read again when the game list reloads.

## Later (the user, 2026-11-07)
The account should come from an account choice on Home, which does not exist yet. Until then the account works as written above. Keep the reader of the collections taking the account as one argument, so that change is small.

## Left to the builder
Exact sizes, names of objects and tests, how the model of the buttons is exposed to QML, the Portuguese texts, the README and changelog lines, a test for the packaged build if one applies.
