# steam-case-covers

Gives every game in your Steam library a "physical copy" portrait cover: the game's art inside a blue case with a Steam banner.

Everything runs locally. No login, no API key, no uploads. Art comes from Steam's own servers.

Not affiliated with Valve, Microsoft or any publisher. See [THIRD_PARTY.md](THIRD_PARTY.md).

Covers I already made are on SteamGridDB: <https://www.steamgriddb.com/profile/76561198040695197/grids/1>. You can download them from there instead of generating your own.

## Use

Needs Python 3.8+ and Pillow. On macOS/Linux use `python3` instead of `python`.

```bash
python -m pip install pillow
python steamcase.py make     # builds covers into ./covers
# close Steam, then:
python steamcase.py apply    # copies them into Steam
```

Start Steam again. `python steamcase.py run` does both steps.

By default only installed games are found. To include your whole library:

1. Log in at <https://store.steampowered.com>, then open <https://store.steampowered.com/dynamicstore/userdata/>.
2. Press Ctrl+S and save the page as `userdata.json`.
3. Run `python steamcase.py run --library userdata.json`.

That file has your account data. Don't share it.

Other commands and options: `python steamcase.py -h`.

## Notes

- Close Steam before `apply`. Replaced files are backed up in `userdata/<id>/config/grid_backup_<date>/`.
- Many old games have no real portrait on Steam, so their covers look blurry. Add `--skip-auto-art` to skip them.
- Custom art set by hand in Steam overrides these covers.
- Covers are local to the machine. Copy the `grid` folder to use them elsewhere.
- Steam Deck: use Desktop Mode, and install Pillow in a venv (`python -m venv .venv`).
- Tested on Linux (SteamOS). Windows and macOS should work, but please open an issue if something breaks.
- Covers contain publishers' art. Keep them for personal use.

MIT license. Third-party files and trademarks: [THIRD_PARTY.md](THIRD_PARTY.md).
