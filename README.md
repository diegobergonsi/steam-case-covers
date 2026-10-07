# steam-case-covers

Gives every game in your Steam library a "physical copy" portrait cover: the game's art inside a blue case with a Steam banner.

Everything runs locally. No login, no API key, no uploads. Art comes from Steam's own servers.

Not affiliated with Valve, Microsoft or any publisher. See [THIRD_PARTY.md](THIRD_PARTY.md).

## Use

Needs Python 3.8+ and Pillow.

```bash
python -m pip install pillow
python steamcase.py make     # builds covers into ./covers
# close Steam, then:
python steamcase.py apply    # copies them into Steam
```

Start Steam again. `python steamcase.py run` does both steps.

By default only installed games are found. For your whole library, open <https://store.steampowered.com/dynamicstore/userdata/> while logged in, save it as `userdata.json`, and add `--library userdata.json`.

Other commands and options: `python steamcase.py -h`.

## Notes

- Close Steam before `apply`. Replaced files are backed up in `userdata/<id>/config/grid_backup_<date>/`.
- Many old games have no real portrait on Steam, so their covers look blurry. Add `--skip-auto-art` to skip them.
- Custom art set by hand in Steam overrides these covers.
- Covers are local to the machine. Copy the `grid` folder to use them elsewhere.
- Steam Deck: use Desktop Mode, and install Pillow in a venv (`python -m venv .venv`).
- Covers contain publishers' art. Keep them for personal use.

MIT license. Third-party files and trademarks: [THIRD_PARTY.md](THIRD_PARTY.md).
