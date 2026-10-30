# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Step 4 of the window: making the covers. Reads what steps 1 to 3 chose, asks before replacing covers already made, builds the covers on a
worker thread with progress, and tells how it went. The words are those of the Tk window."""
import os
import threading

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

import steamcase as sc
from qtui import reasons

STATUS_IDLE = "Not started."
MAX_NAME = 60                               # a long game name is cut in the progress line


def result_text(res, problems):
    """(sentence, kind) for the result of sc.make_covers; `problems`: art of the user's that could not be copied. Kind is "ok" for a clean run."""
    n, miss, bad = res["ok"], len(res["missing"]), len(res["failed"])
    text = "%s%d covers ready." % ("Stopped. " if res["cancelled"] else "Done. ", n)
    if miss:
        text += " %d %s no portrait on Steam." % (miss, "game has" if miss == 1 else "games have")
    fam = res.get("family", 0)
    if fam:
        text += " %d of them %s and %s a green corner." % (fam, "is a family game" if fam == 1 else "are family games", "has" if fam == 1 else "have")
    done = res.get("completed", 0)
    if done:
        text += " %d of them %s 100%% and %s highlighted." % (done, "is" if done == 1 else "are", "is" if done == 1 else "are")
    skipped = res.get("not_games", 0) + res.get("unlisted", 0)
    if skipped:
        text += " Skipped %d items that aren't games you can play (DLC, soundtracks, tools, and apps Steam no longer lists)." % skipped
    if bad:
        text += " %d could not be downloaded (connection problem?): click “Make again” to retry only those." % bad
    if problems:
        k = len(problems)
        text += " Could not keep a copy of your own art for %d %s: Apply moves %s into the backup, and Restore brings %s back." % (
            k, "game" if k == 1 else "games", "that file" if k == 1 else "those files", "it" if k == 1 else "them")
    return text, "ok" if n and not bad else "wait"


class Make(QObject):
    runningChanged = Signal()               # running, searching, asking and canMake
    doneChanged = Signal()
    progressChanged = Signal()
    statusChanged = Signal()
    choicesChanged = Signal()
    confirmNeeded = Signal(str, str)        # the title and the sentence of the question "replace the covers you made?"
    _art_done = Signal(int, object, object, object, object)         # request, {appid: path}, the library's app ids, problems, error words (from the worker)
    _progressed = Signal(int, int, int, str)                        # request, done, total, name
    _made = Signal(int, object, object)                             # request, the result of make_covers, error words

    def __init__(self, shell, covers_dir, account=None, parent=None):
        super().__init__(parent)
        self._shell = shell
        self._covers = covers_dir
        self._account = account or (lambda: None)       # the Steam account folder the user chose, or None
        self._files = []
        self._running = self._searching = self._asking = self._making = False
        self._cancel = threading.Event()
        self._req = 0
        self._snap = None
        self._pending = None                            # (snapshot, own art, problems) waiting for the answer to the question
        self._before = (STATUS_IDLE, "wait")            # the status to go back to when the question is declined
        self._status, self._kind = STATUS_IDLE, "wait"
        self._finished = self._total = 0
        self._art_done.connect(self._on_art)
        self._progressed.connect(self._on_progress)
        self._made.connect(self._on_made)
        shell.hundred.busyChanged.connect(self.runningChanged)
        for signal in (shell.look.toneChanged, shell.look.themeChanged, shell.look.treatmentChanged, shell.look.artChanged,
                       shell.hundred.pathChanged, shell.hundred.styleChanged, shell.hundred.marksChanged,
                       shell.library.pathChanged, shell.library.installedOnlyChanged):
            signal.connect(self.choicesChanged)

    # ----- properties -----
    @Property(bool, notify=runningChanged)
    def running(self):
        """From the moment Make covers is pressed until the covers are ready (or it stopped, failed or was declined)."""
        return self._running

    @Property(bool, notify=runningChanged)
    def searching(self):
        return self._searching

    @Property(bool, notify=runningChanged)
    def asking(self):
        return self._asking

    @Property(bool, notify=runningChanged)
    def canCancel(self):
        return self._making

    @Property(bool, notify=runningChanged)
    def canMake(self):
        return not self._running and not self._asking and not self._shell.hundred.busy

    @Property(bool, notify=doneChanged)
    def done(self):
        return bool(self._files)

    @Property(int, notify=doneChanged)
    def fileCount(self):
        return len(self._files)

    @Property(int, notify=progressChanged)
    def finished(self):
        return self._finished

    @Property(int, notify=progressChanged)
    def total(self):
        return self._total

    @Property(float, notify=progressChanged)
    def progress(self):
        return self._finished / self._total if self._total else 0.0

    @Property(str, notify=statusChanged)
    def status(self):
        return self._status

    @Property(str, notify=statusChanged)
    def statusKind(self):
        return self._kind

    def files(self):
        """The covers of the last good run, for Apply."""
        return list(self._files)

    @Property("QVariantList", notify=choicesChanged)
    def choices(self):
        """What the earlier steps chose, with the step that changes each (an index of shell.steps)."""
        look, hundred, library = self._shell.look, self._shell.hundred, self._shell.library
        if library.installedOnly:
            games = "Installed games"
        else:
            games = "Your game list" if library.path else "Not chosen yet"
        if not hundred.loaded:
            marked = "Skipped"
        elif hundred.style == "none":
            marked = "No special case"
        else:
            marked = reasons.look_label(hundred.values()[1])
        art = [text for text, on in (("Your own art", look.useCustomArt), ("blurry art skipped", look.skipAutoArt)) if on]
        art = ", ".join(art)
        art = (art[0].upper() + art[1:]) if art else "Steam's art"
        theme = "Classic case" if look.theme == "classic" else look.theme.capitalize()
        return [{"key": "games", "label": "Games", "value": games, "step": 1},
                {"key": "colour", "label": "Colour", "value": look.toneName, "step": 2},
                {"key": "theme", "label": "Theme", "value": theme, "step": 2},
                {"key": "hundred", "label": "100% games", "value": marked, "step": 3},
                {"key": "art", "label": "Art", "value": art, "step": 2}]

    # ----- state helpers -----
    def _set_status(self, text, kind):
        if (text, kind) != (self._status, self._kind):
            self._status, self._kind = text, kind
            self.statusChanged.emit()

    def _set_state(self, running=None, searching=None, asking=None, making=None):
        before = (self._running, self._searching, self._asking, self._making)
        self._running = self._running if running is None else running
        self._searching = self._searching if searching is None else searching
        self._asking = self._asking if asking is None else asking
        self._making = self._making if making is None else making
        if before != (self._running, self._searching, self._asking, self._making):
            self.runningChanged.emit()

    # ----- Make covers -----
    @Slot()
    def start(self):
        """Read the choices now, on the UI thread (the worker never touches the window's objects), then look for the user's own art if wanted."""
        if not self.canMake:
            return
        look, hundred, library, shell = self._shell.look, self._shell.hundred, self._shell.library, self._shell
        completed, treatment = hundred.values()
        snap = {"tone": (look.hue, look.sat, look.val), "completed": completed, "treatment": treatment,
                "theme": None if look.theme == "classic" else look.theme,
                "skip": shell.switchValue("skip_auto_art"), "custom": shell.switchValue("use_custom_art"),
                "lib": None if library.installedOnly else library.path, "account": self._account()}
        self._snap = snap
        self._before = (self._status, self._kind)
        self._req += 1
        if not snap["custom"]:
            self._set_state(running=True)
            self._begin(snap, {}, None, ())              # {}: the option is off, covers made from your own art go back to Steam's portrait
            return
        self._set_state(running=True, searching=True)
        self._set_status("Looking for your own art…", "wait")
        threading.Thread(target=self._art_worker, args=(self._req, snap), daemon=True).start()

    def _art_worker(self, req, snap):
        """Off the UI thread: the user's own art for the games in the library. Only the art of games in the library is kept."""
        art = games = problems = error = None
        try:
            steam = sc.steam_dir()
            games, _ = sc.load_library(steam, snap["lib"])
            problems = []
            art = {a: p for a, p in sc.find_custom_art(steam, snap["account"], problems=problems).items() if a in games}
            games = set(games)
        except sc.SteamcaseError as e:
            error = str(e)
        except Exception as e:                          # never leave the window stuck in "running"
            error = "Unexpected problem: %s" % e
        try:
            self._art_done.emit(req, art, games, problems, error)
        except RuntimeError:
            pass                                        # the window is closing: nobody is left to hear the answer

    def _on_art(self, req, art, games, problems, error):
        if req != self._req or not self._searching:
            return
        self._set_state(searching=False)
        if error:
            self._set_state(running=False)
            self._set_status(error, "error")
            return
        self._begin(self._snap, art, games, problems)

    def _begin(self, snap, custom_art, games, problems):
        """The rest of start() once the art is known: ask before replacing covers, then make them."""
        why = reasons.replace_reason(self._covers, snap["tone"], snap["completed"], snap["treatment"], snap["theme"], custom_art, games)
        if why:
            self._pending = (snap, custom_art, list(problems))
            self._set_state(asking=True)
            self.confirmNeeded.emit(why[0], why[1])
            return
        self._run(snap, custom_art, problems)

    @Slot()
    def confirm(self):
        if self._asking and self._pending:
            snap, art, problems = self._pending
            self._pending = None
            self._set_state(asking=False)
            self._run(snap, art, problems)

    @Slot()
    def decline(self):
        if self._asking:
            self._pending = None
            self._set_state(asking=False, running=False)
            self._set_status(*self._before)

    def _run(self, snap, custom_art, problems):
        self._problems = list(problems)
        self._cancel.clear()
        self._finished, self._total = 0, 0
        self.progressChanged.emit()
        self._set_state(running=True, making=True)
        self._set_status("Looking up your games on Steam…", "wait")
        threading.Thread(target=self._make_worker, args=(self._req, snap, custom_art), daemon=True).start()

    def _make_worker(self, req, snap, custom_art):
        """Off the UI thread; talks to the window only through signals."""
        hue, sat, val = snap["tone"]
        res = error = None
        try:
            steam = sc.steam_dir()
            games, family = sc.load_library(steam, snap["lib"])
            if not games:
                raise sc.SteamcaseError("No games found. Install a game first, or load your userdata.json.")
            res = sc.make_covers(games, self._covers, skip_auto_art=snap["skip"], family=family, hue=hue, sat=sat, val=val,
                                 progress=lambda done, total, appid, name, status: self._tell(req, done, total, name),
                                 cancelled=self._cancel.is_set, completed=snap["completed"], treatment=snap["treatment"],
                                 theme=snap["theme"], custom_art=custom_art)
        except sc.SteamcaseError as e:
            error = str(e)
        except Exception as e:
            error = "Unexpected problem: %s" % e
        try:
            self._made.emit(req, res, error)
        except RuntimeError:
            pass

    def _tell(self, req, done, total, name):
        try:
            self._progressed.emit(req, done, total, name)
        except RuntimeError:
            self._cancel.set()                          # the window is gone: stop making covers nobody will see

    def _on_progress(self, req, done, total, name):
        if req != self._req:
            return
        self._finished, self._total = done, max(total, 1)
        self.progressChanged.emit()
        self._set_status("%d of %d · %s" % (done, total, name if len(name) <= MAX_NAME else name[:MAX_NAME - 3] + "…"), "wait")

    def _on_made(self, req, res, error):
        if req != self._req:
            return
        self._set_state(running=False, making=False)
        if error:
            self._set_status(error, "error")
            return
        if res["files"]:                                # a run that made nothing keeps the covers of the run before
            self._files = list(res["files"])
            self.doneChanged.emit()
            self._shell.setFact("covers_made", True)
        self._finished = self._total = max(self._total, self._finished)
        self.progressChanged.emit()
        self._set_status(*result_text(res, self._problems))

    @Slot()
    def cancel(self):
        if self._making and not self._cancel.is_set():
            self._cancel.set()
            self._set_status("Stopping…", "wait")

    @Slot()
    def openFolder(self):
        folder = os.path.abspath(self._covers)
        os.makedirs(folder, exist_ok=True)
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(folder)):
            self._set_status("Could not open the folder. It is here: %s" % folder, "error")
