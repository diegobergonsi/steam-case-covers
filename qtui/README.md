# qtui: the window of the app

The window of the app, in Qt Quick: Home, then the steps of the way you choose (game list, look, 100% games, make, add to Steam, or the way that picks games by hand), plus Restore, Reset, the update check and the link to Discord. The engine (`engine/`, run with `python -m engine`) is shared with the command line.

    python -m pip install -r requirements-qt.txt      # Python 3.10 or newer
    python -m qtui                                    # the window
    python -m qtui --selftest                         # builds it without showing it; prints "selftest ok"
    pyinstaller steamcase-qt.spec                     # one file (Windows, Linux) or an .app folder (macOS)

The rules the screens follow are in `docs/ui-guide.md`. Colours, sizes and durations live only in `qtui/qml/Theme.qml`. The pictures of the README are taken with `python tools/take_screenshots.py OUT_DIR`.
