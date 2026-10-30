# qtui: the new window (work in progress)

A Qt Quick window that will replace the Tk window (`gui.py`). Not finished: steps 1 to 5 work (game list, look, 100% games, make, add to Steam); Home is still a placeholder. The engine (`steamcase.py`) is shared and unchanged.

    python -m pip install -r requirements-qt.txt      # Python 3.10 or newer
    python -m qtui                                    # the window
    python -m qtui --selftest                         # builds it without showing it; prints "selftest ok"
    pyinstaller steamcase-qt.spec                     # one file (Windows, Linux) or an .app folder (macOS)

The rules the screens follow are in `docs/ui-guide.md`. Colours, sizes and durations live only in `qtui/qml/Theme.qml`.
