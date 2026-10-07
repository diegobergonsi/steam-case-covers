# steam-case-covers

Give every game in your Steam library a **"physical copy" portrait cover**: the game's own art inside a blue case with a Steam banner, like a boxed console game.

It works locally. There is no account login, no Steam API key, and nothing is uploaded. The script reads your Steam library, downloads each game's portrait image from Steam's own servers, puts it in the frame, and copies the result into Steam's custom-artwork folder.

> Not affiliated with Valve, Microsoft or any publisher. See [THIRD_PARTY.md](THIRD_PARTY.md).

## Requirements
- Python 3.8+
- [Pillow](https://pillow.readthedocs.io): `python -m pip install pillow`
- Steam installed (Windows, macOS or Linux/SteamOS)

## Quick start

```bash
git clone https://github.com/YOUR-USER/steam-case-covers
cd steam-case-covers
python -m pip install -r requirements.txt

python steamcase.py list          # what it found
python steamcase.py make          # builds ./covers/Game_Name_<appid>.png
# close Steam, then:
python steamcase.py apply         # copies covers into Steam's grid folder
```
Start Steam again. Or do both steps at once with `python steamcase.py run`.

### Your whole library (not just installed games)
By default only **installed** games are found. For everything you own:

1. Log in at <https://store.steampowered.com> in your browser.
2. Open <https://store.steampowered.com/dynamicstore/userdata/> and save the page as `userdata.json` (Ctrl+S).
3. Run:
   ```bash
   python steamcase.py run --library userdata.json
   ```
This file contains your account's data. It is git-ignored, so don't share it.

## Commands and options

| Command | What it does |
|---|---|
| `list` | Print detected games |
| `make` | Build covers into `--out` (default `./covers`) |
| `apply` | Copy covers into Steam as `<appid>p.png`, backing up anything it replaces |
| `run` | `make` then `apply` |

| Option | Meaning |
|---|---|
| `--library FILE` | Use the whole-library JSON described above |
| `--steam-dir PATH` | Steam folder, if auto-detection fails |
| `--user ID` | Account folder inside `userdata/` (default: the most recent login) |
| `--only APPID ...` | Only these games |
| `--force` | Rebuild covers that already exist |
| `--skip-auto-art` | Skip games where Steam has no real portrait (see below) |
| `--yes` | Don't ask when Steam is running |

## Notes and limits
- **Close Steam before `apply`.** Steam reads the folder at startup. Restart it afterwards.
- **Old games.** Steam has no real portrait for many older games. It makes one from the wide header image, so the cover looks like a banner on a blurred background. Use `--skip-auto-art` to leave those alone.
- **Custom art you set by hand** in Steam can override these covers. Reset it in the game's Manage > Set custom artwork menu.
- **Backups.** Replaced files are saved to `userdata/<id>/config/grid_backup_<date>/`. To undo, copy them back.
- **Other devices.** Custom art is local. Copy the `grid` folder to another machine to get the same covers there.
- **Steam Deck / SteamOS.** Use Desktop Mode. SteamOS has no `pip` out of the box; use a venv: `python -m venv .venv && .venv/bin/pip install pillow && .venv/bin/python steamcase.py run`.
- **Non-Steam shortcuts** (Chrome, Stremio...) aren't handled automatically.
- Covers contain publishers' artwork. Keep them for personal use.

## Changing the design
`assets/frame.png` is the prebuilt frame (600x900, transparent art window). To edit it, change `tools/build_frame.py` and run it (needs `rsvg-convert` from librsvg). Using the tool does not need that.

## License
MIT for the code (see [LICENSE](LICENSE)). Trademarks and bundled third-party files: [THIRD_PARTY.md](THIRD_PARTY.md).
