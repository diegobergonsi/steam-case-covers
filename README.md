<p align="center">
  <img src="assets/preview.png" alt="Steam Case Covers: your Steam library as a fan of physical game boxes">
</p>

<h1 align="center">steam-case-covers</h1>

<p align="center">
  Give every game in your Steam library a "physical copy" case cover.<br>
  Everything runs on your computer: no login, no API key, no uploads.
</p>

<p align="center">
  <a href="https://github.com/diegobergonsi/steam-case-covers/releases"><b>DOWNLOAD</b></a>
</p>

<p align="center">
  <a href="#install">Install</a> ·
  <a href="#how-it-works">How it works</a> ·
  <a href="#features">Features</a> ·
  <a href="#safety">Safety</a> ·
  <a href="#steam-compatibility">Steam compatibility</a> ·
  <a href="#command-line">Command line</a> ·
  <a href="#faq">FAQ</a>
</p>

<p align="center">
  <img src="assets/screenshot.png" width="460" alt="The steam-case-covers window with its three steps">
  <br>
  <em>The whole app: three steps, no terminal.</em>
</p>

<p align="center">
  <em>
    This project is not affiliated with Valve Corporation, Microsoft or any game publisher.
    Steam and Windows are trademarks of their respective owners. See <a href="THIRD_PARTY.md">THIRD_PARTY.md</a>.
  </em>
</p>

## What is it?

Steam shows your library as tall portrait cards. This tool puts each game's own artwork inside a blue "box" with a Steam banner and platform badges, like a boxed console game, and installs the result as your custom artwork.

The artwork comes from Steam's own servers. The covers are built on your computer and stay there.

<p align="center">
  <img src="assets/steam-library.png" width="460" alt="A Steam library with the covers installed: every game is a blue case with a Steam banner and platform badges">
  <br>
  <em>How the covers look inside Steam.</em>
</p>

## Install

<details>
<summary><b>Windows</b></summary>

Download `SteamCaseCovers-windows.exe` from the [Releases page](https://github.com/diegobergonsi/steam-case-covers/releases) and double-click it.

If "Windows protected your PC" appears, click **More info**, then **Run anyway**. The app isn't code-signed (that costs money), which is why Windows warns you. Some antivirus tools also flag apps of this kind.

</details>

<details>
<summary><b>macOS</b></summary>

Download `SteamCaseCovers-macos.zip` from the [Releases page](https://github.com/diegobergonsi/steam-case-covers/releases) and double-click it to unzip. **Before you open the app**, run this in **Terminal** (change the path if the app isn't in Downloads), then double-click the app:

```bash
xattr -dr com.apple.quarantine ~/Downloads/SteamCaseCovers.app
```

Why: macOS blocks any app that doesn't come from a paid Apple developer (about 99 USD a year, which a free project can't justify). That command removes the "downloaded from the internet" mark, so macOS opens the app normally. The app isn't harmful or damaged, and its source code is here for anyone to read.

If you open the app first instead, macOS shows **"SteamCaseCovers" Not Opened: Apple could not verify it is free of malware**. Click **Done** (not Move to Trash), then open **System Settings**, **Privacy & Security**, scroll to **Security**, and click **Open Anyway** next to the SteamCaseCovers message (it stays for about an hour; double-click the app again to bring it back). If the app then bounces in the Dock forever with no window, **restart your Mac** and use the Terminal command above instead. On macOS 14 or older you can also right-click the app and choose **Open**.

The first time you press **Apply to Steam**, macOS may say the app isn't allowed to control Steam. Allow it in the prompt (or in **System Settings**, **Privacy & Security**), then press the button again.

macOS support is **best effort**: the author has only tested it on an Apple Silicon MacBook Air. The build is for Apple Silicon (M1 or newer). On an Intel Mac, run it [from source](#from-source).

</details>

<details>
<summary><b>Linux and Steam Deck</b></summary>

On a Steam Deck, switch to **Desktop Mode** first. The app needs a desktop window, so it doesn't run in Gaming Mode.

Download `SteamCaseCovers-linux` from the [Releases page](https://github.com/diegobergonsi/steam-case-covers/releases) and open it. On a Steam Deck a small pop-up appears: click **Launch** and the app opens.

If your file manager doesn't run it, make it executable and start it from a terminal:

```bash
chmod +x SteamCaseCovers-linux
./SteamCaseCovers-linux
```

</details>

<details id="from-source">
<summary><b>From source (any system)</b></summary>

If you'd rather not trust a download, run it from the code. It needs Python 3.8+ and Pillow 10.3 or newer.

```bash
git clone https://github.com/diegobergonsi/steam-case-covers
cd steam-case-covers
python -m pip install -r requirements.txt
python gui.py
```

On macOS and Linux, use `python3` instead of `python`. Run the tests with `python -m unittest discover -s tests`. A random-click robot that tries to break the window needs a display: `python tests/fuzz_gui.py` (on a server: `xvfb-run -a python tests/fuzz_gui.py`).

</details>

Release files come with a `SHA256SUMS` list so you can check what you downloaded. See [SECURITY.md](SECURITY.md).

## How it works

1. **Get your game list.** Click **Download your game list**. Your browser opens Steam: log in if it asks, and you'll land on a page of plain text. Save it (Ctrl+S, or Cmd+S on a Mac) as `userdata.json`. The app notices the file by itself. No browser opening? Click **Copy link** and paste it yourself. Or tick **Only my installed games** to skip this step. On a Mac with Safari, set the format to **Page Source** when saving (or use Chrome or Firefox).
2. **Make the covers.** Click **Make covers** and wait. You can cancel and run it again later: finished covers are kept, so it picks up where it stopped.
3. **Add them to Steam.** Click **Apply to Steam**. If more than one Steam account is on this computer, the window shows which one will change; click **Change account** to pick another.

> [!WARNING]
> Step 3 **closes Steam for you** (any running game stops and downloads pause), adds the covers, and starts Steam again. Save your game first. The app asks before it does anything.

Changed your mind?

* **Restore previous artwork** undoes the last Apply. Press it again to go one step further back.
* **Reset to Steam's default art** removes the covers this app made. It works even if you have no backup. If it also finds custom art that this app did not make (from SteamGridDB, or set by hand in Steam), it asks whether to remove that too: **Remove only ours** keeps it, **Remove all** brings back Steam's own art everywhere. Restore undoes either.

## Features

✅ Covers for your installed games, or your whole library <br>
✅ Each cover is the game's own portrait inside a case, with the Steam banner and platform badges <br>
✅ One click to install them: Steam is closed gracefully, backed up, updated and restarted <br>
✅ Undo, step by step, and a reset to Steam's default art <br>
✅ Cancel anytime; run again to continue <br>
✅ Optional "skip blurry covers" for games Steam has no real portrait for <br>
✅ Pick the colour of the cases with a slider or a ready-made swatch, with a live preview. Only the original blue is checked for readable text <br>
✅ Several Steam accounts on one computer: you choose which one gets the covers <br>
✅ Games shared through Steam Family Sharing get covers too, with a green corner and a family icon so you can tell them apart. The app finds them in Steam's own files on your computer, with nothing extra to download. This is only tested on a small family, so please open an issue if games are missing from a big shared library. Save your game list again after you buy games, so the new ones are not mistaken for family games <br>
✅ Works with the keyboard, scales on high-DPI screens and fits small screens like the Steam Deck's <br>
✅ A "Check for updates" button, only when you click it: it asks GitHub for the newest version and never downloads or installs anything
✅ Free software: no ads, no account, no telemetry

## Safety

* It only ever touches the portrait files (`<appid>p.png`, and `.jpg`, `.jpeg` or `.webp` ones that would hide a cover) in your Steam account's `config/grid` folder. Anything it moves is kept in the backup. It never touches your games or saves.
* Before every change it makes a backup of exactly what it changes, writes files atomically, and rolls back if anything fails.
* Two open windows can't change Steam's folder at the same time.
* It never logs in, never asks for a password or API key, never uploads anything and never runs with elevated rights.
* Files it reads from the internet are size-limited and checked before use.

If you find a security problem, please [report it privately](SECURITY.md).

## Steam compatibility

✅ Linux and SteamOS (Steam in `~/.local/share/Steam`) <br>
✅ Windows: tested by the author's colleague on a real PC, and the automated tests pass <br>
🟡 macOS: tested on one Apple Silicon Mac (best effort)

> [!NOTE]
> If something doesn't work on your system, please [open an issue](https://github.com/diegobergonsi/steam-case-covers/issues) with your system and what you saw. Feedback from Windows and macOS is especially welcome.

## Command line

Everything the window does is also available in a terminal:

```bash
python steamcase.py make --library userdata.json   # build covers
python steamcase.py make --library userdata.json --hue 134   # ...in another case colour (0 to 359 degrees; 0 is the original blue)
python steamcase.py apply --close-steam            # install them
python steamcase.py restore                        # undo the last apply
python steamcase.py reset                          # back to Steam's default art
python steamcase.py reset --everything             # ...also removing art from other sources
```

| Command | What it does |
|---|---|
| `list` | Show the games it found |
| `make` | Build covers into `./covers` |
| `apply` | Copy covers into Steam, with a backup |
| `run` | `make` then `apply` |
| `restore` | Undo the last apply (run again to go further back) |
| `reset` | Remove the covers this app made from Steam (`--everything` also removes custom art from other sources) |

Run `python steamcase.py -h` for all options, such as `--only`, `--hue`, `--skip-auto-art`, `--steam-dir` and `--user` (the account's folder number in Steam's `userdata`, to pick one of several accounts).

## FAQ

<details>
<summary><b>It says my game list has no games in it</b></summary>

You weren't logged in to Steam in your browser when you saved the page. Steam doesn't show an error in that case; it gives an empty list. Click **Download your game list** again: it opens Steam's login page first, so log in there, then save the page you land on. If that page shows no games even though you just logged in, refresh it (F5, or Cmd+R on a Mac) before saving.

</details>

<details>
<summary><b>Why do some covers look blurry?</b></summary>

Many older or smaller games have no real portrait on Steam. Steam builds a stand-in from the wide header image, so the title banner sits in the middle of a blurred copy of itself. Tick **Skip blurry covers** (hover the **i** next to it) to leave those games alone.

</details>

<details>
<summary><b>I set custom art by hand in Steam. Will these replace it?</b></summary>

Steam shows art you set by hand (or got from SteamGridDB) before these covers. **Apply to Steam** moves such art for the covered games into the backup, so the case is shown, and **Restore** brings it back. To clear all of it and get Steam's own art, use **Reset to Steam's default art** and choose **Remove all**.

</details>

<details>
<summary><b>Where are the covers stored?</b></summary>

In your own user folder: `~/.local/share/steamcase/covers` on Linux, `%LOCALAPPDATA%\steamcase\covers` on Windows and `~/Library/Application Support/steamcase/covers` on macOS. Use **Open covers folder** in the app. Steam's copies live in `userdata/<id>/config/grid`; copy that folder to use the covers on another computer.

</details>

<details>
<summary><b>Does it work for non-Steam games and shortcuts?</b></summary>

Not yet. Only games in your Steam library.

</details>

<details>
<summary><b>Can I get the covers without running it?</b></summary>

Covers I already made are on SteamGridDB: <https://www.steamgriddb.com/profile/76561198040695197/grids/1>.

</details>

<details>
<summary><b>Are screen readers supported?</b></summary>

No. The window works fully with the keyboard (Tab, Space, Enter), but the toolkit it uses can't talk to screen readers. The command line is the accessible alternative.

</details>

## Acknowledgments

Thanks to [SteamGridDB](https://www.steamgriddb.com) and its community for making custom Steam artwork easy to share, and to the authors of [Pillow](https://python-pillow.org), [PyInstaller](https://pyinstaller.org), the [Nunito Sans](https://fonts.google.com/specimen/Nunito+Sans) font and the KDE Breeze icon theme. Details are in [THIRD_PARTY.md](THIRD_PARTY.md).

Game artwork shown above belongs to its publishers and developers. Covers you generate contain that artwork: keep them for personal use.

## License

Copyright (C) 2026 Diego Bergonsi. Free software under the [GNU General Public License v3 or later](LICENSE): you may use, change and share it, and anything you distribute built on it must stay open under the same license.
