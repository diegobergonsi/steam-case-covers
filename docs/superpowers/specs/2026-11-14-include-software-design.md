# Include software in the covers (issue #73, problem 2)

## Why
A user reported that Steam software such as Lossless Scaling (AppID 993090) gets no case, so their library looks uneven. Steam types software as 6 (Lossless Scaling, Wallpaper Engine and Blender all have normal portrait art). The engine skips every type except games (0, none) and playtests (12).

## Goal
A switch, off by default, that makes covers for software (type 6) as well. Nothing changes for people who leave it off.

## Non-goals
- Real tools (Proton, Steam Linux Runtime): they have no store page and no art, so there is nothing to put in a case. They stay skipped.
- Demos, DLC and other types stay skipped.
- Listing software in the "Pick games" list (see Known limit).

## Approaches
1. **Switch on the Look screen, "Art" section, next to "Skip blurry covers"** (chosen by the user). Easy to find, and Look is where the other art switches live. Known limit below.
2. Switch on the Game list step next to "Only my installed games" (my pick, not chosen). It would also let people pick software by hand, but it sits away from the other art switches.

## Design
- Engine: `GAME_TYPES` stays. A second constant `SOFTWARE_TYPE = 6`. `list_games` and `make_covers` get `software=False`; when true the type check also accepts 6. The three type checks go through one small helper so the rule lives in one place.
- Command line: `--include-software` (store_true), passed to `make_covers`.
- Window: new setting `include_software` (default False) in `qtui/settings.py`; a property on `Look` like `skipAutoArt`; a `SwitchRow` "Include software" with a help tip in `LookScreen.qml`; the Make step passes it in its snapshot and shows it in the summary line with the other art choices.
- Translations: the new strings go into `qtui/i18n_pt_br.py` (the project keeps a test that checks this).

## Known limit
The Pick games list is built in step 1, before Look, so in that flow software is not listed and cannot be picked. The switch works for the "Same case" flow. Moving the switch to step 1 is the upgrade if people ask.

## Left to the builder
Exact wording of the label and the help tip (plain words, no jargon); where the helper lives.

## Checks
Tests first: software skipped by default, covered with the switch, tools still skipped, setting saved and restored, Make passes it through, command line flag, pt-BR strings present. Then the whole suite with Qt (`.venv`).
