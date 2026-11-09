# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Step 4 of the window: making the covers. Reads what steps 1 to 3 chose, asks before replacing covers already made, builds the covers on a
worker thread with progress, and tells how it went. The words are those the app has always used."""
import os
import threading

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from engine import groups
from engine import steamcase as sc
from qtui import reasons
from qtui.groupticks import GroupTicks
from qtui.i18n import N_, retranslated, tr, trn

STATUS_IDLE = N_("Not started.")
MAX_THUMBS = 5                              # covers shown under the status
MAX_NAME = 60                               # a long game name is cut in the progress line


def result_text(res, problems):
    """(sentence, kind) for the result of sc.make_covers; `problems`: art of the user's that could not be copied. Kind is "ok" for a clean run."""
    n, miss, bad = res["ok"], len(res["missing"]), len(res["failed"])
    text = "%s %s" % (tr("Stopped.") if res["cancelled"] else tr("Done."), trn("%n cover ready.|%n covers ready.", n))
    if miss:
        text += " " + trn("%n game has no portrait on Steam.|%n games have no portrait on Steam.", miss)
    fam = res.get("family", 0)
    if fam:
        text += " " + trn("%n of them is a family game and has a green corner.|%n of them are family games and have a green corner.", fam)
    consoles = res.get("platforms", 0)
    if consoles:
        text += " " + trn("%n of them is in a console case.|%n of them are in a console case.", consoles)
    done = res.get("completed", 0)
    if done:
        text += " " + trn("%n of them is 100% and is highlighted.|%n of them are 100% and are highlighted.", done)
    skipped = res.get("not_games", 0) + res.get("unlisted", 0)
    if skipped:
        text += " " + trn("Skipped %n item that isn't a game you can play (DLC, soundtracks, tools, and apps Steam no longer lists).|"
                          "Skipped %n items that aren't games you can play (DLC, soundtracks, tools, and apps Steam no longer lists).", skipped)
    if bad:
        text += " " + trn("%n could not be downloaded (connection problem?): click \u201cMake again\u201d to retry only that one.|"
                          "%n could not be downloaded (connection problem?): click \u201cMake again\u201d to retry only those.", bad)
    if problems:
        text += " " + trn("Could not keep a copy of your own art for %n game: Apply moves that file into the backup, and Restore brings it back.|"
                          "Could not keep a copy of your own art for %n games: Apply moves those files into the backup, and Restore brings them back.", len(problems))
    return text, "ok" if n and not bad else "wait"


def _marks_only(treatment):
    """The treatment a console case or your own case can have: the marks of `treatment` on the plain case, no gold (None stays None)."""
    return sc.compose_treatment("ribbon", sc.split_treatment(treatment)[1]) if treatment else None


class Make(QObject):
    runningChanged = Signal()               # running, searching, asking and canMake
    doneChanged = Signal()
    progressChanged = Signal()
    statusChanged = Signal()
    choicesChanged = Signal()
    groupsChanged = Signal()                # the groups listed in the usual Make, and which are ticked
    groupsDeleted = Signal(object)          # the games of the groups a Make repainted and so deleted (the shell tells the Case step)
    failed = Signal(str, str)               # a title and the words of an error, for a box the user cannot miss wherever they are
    confirmNeeded = Signal(str, str)        # the title and the sentence of the question "replace the covers you made?"
    _art_done = Signal(int, object, object, object, object)         # request, {appid: path}, the library's app ids, problems, error words (from the worker)
    _progressed = Signal(int, int, int, str)                        # request, done, total, name
    _made = Signal(int, object, object)                             # request, the result of make_covers, error words

    def __init__(self, shell, covers_dir, account=None, apply_busy=None, parent=None):
        super().__init__(parent)
        self._shell = shell
        self._apply_busy = apply_busy or (lambda: False)     # covers must not change while they are being added to Steam
        self._covers = covers_dir
        self._account = account or (lambda: None)       # the Steam account folder the user chose, or None
        self._files = []
        self._stopped = False                           # the last run was stopped with Cancel (what it made is still ready)
        self._running = self._searching = self._asking = self._making = False
        self._cancel = threading.Event()
        self._ticks = GroupTicks(covers_dir, self)      # the saved groups, listed in the usual Make with a box each: the ones ticked are repainted
        self._req = 0
        self._snap = None
        self._pending = None                            # (snapshot, own art, problems) waiting for the answer to the question
        self._question = ("", "")                      # what is being asked, kept here so a screen that opens late can still show it
        self._can = True
        self._before = (tr(STATUS_IDLE), "wait")            # the status to go back to when the question is declined
        self._status, self._kind = tr(STATUS_IDLE), "wait"
        self._finished = self._total = 0
        self._art_done.connect(self._on_art)
        shell.languageChanged.connect(self._language_changed)
        self._progressed.connect(self._on_progress)
        self._made.connect(self._on_made)
        shell.hundred.busyChanged.connect(self.refreshAvailability)
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
        return not self._running and not self._asking and not self._shell.hundred.busy and not self._apply_busy()

    @Property(str, notify=runningChanged)
    def questionTitle(self):
        return self._question[0]

    @Property(str, notify=runningChanged)
    def questionText(self):
        return self._question[1]

    def refreshAvailability(self):
        """Tell the window when canMake changed because of something outside (a page being read, covers being added to Steam)."""
        if self.canMake != self._can:
            self._can = self.canMake
            self.runningChanged.emit()

    @Property(bool, notify=doneChanged)
    def done(self):
        return bool(self._files)

    @Property(int, notify=doneChanged)
    def fileCount(self):
        return len(self._files)

    @Property(str, notify=doneChanged)
    def nextText(self):
        """The words of the main button once covers are ready: after a stopped run it says how many covers it would add, since that is not the whole set."""
        n = len(self._files)
        if self._stopped and n:
            return trn("Add the %n cover to Steam \u2192|Add the %n covers to Steam \u2192", n)
        return tr("Next: Add to Steam \u2192")

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

    @Property("QVariantList", notify=doneChanged)
    def thumbs(self):
        """The first covers of the last run, as file URLs, to show what was built."""
        return [QUrl.fromLocalFile(f).toString() for f in self._files[:MAX_THUMBS]]

    def files(self):
        """The covers of the last good run, for Apply."""
        return list(self._files)

    @Property("QVariantList", notify=choicesChanged)
    def choices(self):
        """What the earlier steps chose, with the step that changes each (an index of shell.steps)."""
        look, hundred, library = self._shell.look, self._shell.hundred, self._shell.library
        if self._shell.flow == "manual":
            cases = self._shell.cases
            count = cases.assignedCount
            marked = tr("Skipped") if not hundred.loaded else tr("Left plain") if hundred.style == "none" else tr("Highlighted")
            return [{"key": "games", "label": tr("Games"), "value": trn("%n game|%n games", count), "step": self._shell.stepIndex("pick")},
                    {"key": "cases", "label": tr("Cases"), "value": ", ".join(s["label"] for s in cases.summary), "step": self._shell.stepIndex("case")},
                    {"key": "hundred", "label": tr("100% games"), "value": marked, "step": self._shell.stepIndex("hundred")}]
        if library.installedOnly:
            games = tr("Installed games")
        else:
            games = tr("Your game list") if library.path else tr("Not chosen yet")
        if not hundred.loaded:
            marked = tr("Skipped")
        elif hundred.style == "none":
            marked = tr("No special case")
        else:
            marked = reasons.look_label(hundred.values()[1])
        art = [text for text, on in ((tr("Your own art"), look.useCustomArt), (tr("blurry art skipped"), look.skipAutoArt)) if on]
        art = ", ".join(art)
        art = (art[0].upper() + art[1:]) if art else tr("Steam's art")
        theme = tr("Classic case") if look.theme == "classic" else reasons.theme_label(look.theme)
        return [{"key": "games", "label": tr("Games"), "value": games, "step": 1},
                {"key": "colour", "label": tr("Colour"), "value": look.toneName, "step": 2},
                {"key": "theme", "label": tr("Theme"), "value": theme, "step": 2},
                {"key": "hundred", "label": tr("100% games"), "value": marked, "step": 3},
                {"key": "art", "label": tr("Art"), "value": art, "step": 2}]

    @Property(QObject, constant=True)
    def groupTicks(self):
        """The groups of the manual way with a box each (see GroupTicks)."""
        return self._ticks

    # ----- state helpers -----
    def _set_status(self, text, kind):
        if (text, kind) != (self._status, self._kind):
            self._status, self._kind = text, kind
            self.statusChanged.emit()

    def _language_changed(self):
        """The line that waits for a run is stored translated: it follows the language (a line about a run that happened stays as it was said)."""
        self._before = (retranslated(self._before[0], STATUS_IDLE), self._before[1])
        self._set_status(retranslated(self._status, STATUS_IDLE), self._kind)

    def _set_state(self, running=None, searching=None, asking=None, making=None):
        before = (self._running, self._searching, self._asking, self._making)
        self._running = self._running if running is None else running
        self._searching = self._searching if searching is None else searching
        self._asking = self._asking if asking is None else asking
        self._making = self._making if making is None else making
        if before != (self._running, self._searching, self._asking, self._making):
            self._can = self.canMake
            self.runningChanged.emit()

    def start_over(self):
        """Forget the covers made in this run (the files stay in the covers folder) and the group ticks. The shell does not call this while covers are made."""
        self._files, self._stopped, self._problems = [], False, []
        self._finished = self._total = 0
        self._ticks.clear()
        self.doneChanged.emit()
        self.progressChanged.emit()
        self._set_status(tr(STATUS_IDLE), "wait")

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
        if shell.flow == "manual":                      # only the games given a case; the Look step is not part of this flow, so its theme and blurry-art switches do not count (own art does: the Case step has the switch)
            if not shell.cases.assignedCount:
                return
            snap.update(manual=True, platforms=shell.cases.assigned(), tones=shell.cases.tones(), groups=shell.cases.groupIds(), save=shell.cases.groupsToSave(),
                        released=shell.cases.released(), family=shell.cases.family, theme=None, skip=False,
                        treatment=_marks_only(treatment))
        else:
            self._ticks.refresh()
            snap["repaint"] = self._ticks.ticked()
            snap["own_case"] = look.ownCase
            if snap["own_case"]:                    # your own case has its own colours and no gold look: only the marks count, as for a console case
                snap.update(theme=None, treatment=_marks_only(treatment))
        self._snap = snap
        self._before = (self._status, self._kind)
        self._req += 1
        if not snap["custom"]:
            self._set_state(running=True)
            self._begin(snap, {}, None, ())              # {}: the option is off, covers made from your own art go back to Steam's portrait
            return
        self._set_state(running=True, searching=True)
        self._set_status(tr("Looking for your own art…"), "wait")
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
            error = tr("Unexpected problem: %s") % e
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
            self.failed.emit(tr("Cannot read your own art"), error)
            return
        self._begin(self._snap, art, games, problems)

    def _begin(self, snap, custom_art, games, problems):
        """The rest of start() once the art is known: ask before replacing covers, then make them."""
        if snap.get("own_case"):
            why = reasons.own_case_reason(self._covers, True, snap["treatment"], snap["completed"], custom_art)
        elif snap.get("manual"):
            why = reasons.platform_replace_reason(self._covers, snap["platforms"], snap["tone"], snap["treatment"], snap["completed"], snap["tones"], snap["groups"], custom_art)
        else:
            why = reasons.replace_reason(self._covers, snap["tone"], snap["completed"], snap["treatment"], snap["theme"], custom_art, games)
            for more in (reasons.group_repaint_reason(snap["repaint"]), reasons.own_case_reason(self._covers, False)):
                if more:
                    why = more if why is None else (why[0], why[1] + " " + more[1])
        if why:
            self._pending = (snap, custom_art, list(problems))
            self._question = why
            self._set_state(asking=True)
            self.runningChanged.emit()
            self.confirmNeeded.emit(why[0], why[1])
            return
        self._run(snap, custom_art, problems)

    @Slot()
    def confirm(self):
        if self._asking and self._pending:
            snap, art, problems = self._pending
            self._pending = None
            self._question = ("", "")
            self._set_state(asking=False)
            self._run(snap, art, problems)

    @Slot()
    def decline(self):
        if self._asking:
            self._pending = None
            self._question = ("", "")
            self._set_state(asking=False, running=False)
            self._set_status(*self._before)

    def _run(self, snap, custom_art, problems):
        self._problems = list(problems)
        if self._files:                                 # what Apply may add is what this run makes: a run that fails offers nothing
            self._files = []
            self.doneChanged.emit()
        self._shell.setFact("covers_made", False)       # step 5 is locked again until this run has covers
        self._cancel.clear()
        self._finished, self._total = 0, 0
        self.progressChanged.emit()
        self._set_state(running=True, making=True)
        self._set_status(tr("Looking up your games on Steam…"), "wait")
        threading.Thread(target=self._make_worker, args=(self._req, snap, custom_art), daemon=True).start()

    def _make_worker(self, req, snap, custom_art):
        """Off the UI thread; talks to the window only through signals."""
        hue, sat, val = snap["tone"]
        res = error = None
        try:
            steam = sc.steam_dir()
            games, family = sc.load_library(steam, snap["lib"])
            if not games:
                raise sc.SteamcaseError(tr("No games found. Install a game first, or load your userdata.json."))
            manual = snap.get("manual")
            extra = {"platforms": snap["platforms"], "tones": snap["tones"], "groups": snap["groups"]} if manual else {}
            if snap.get("own_case"):
                extra["platforms"] = {appid: sc.CUSTOM for appid in games}          # every game, in the case the user gave
            elif not manual:                        # covers made in your own case for every game go back to the Steam case now that it is off
                extra["repaint"] = {a for g in snap.get("repaint") or () for a in g["games"]} | sc.covers_in_own_case(self._covers)
            res = sc.make_covers(games, self._covers, skip_auto_art=snap["skip"], family=family if not manual or snap["family"] else set(), hue=hue, sat=sat, val=val,
                                 progress=lambda done, total, appid, name, status: self._tell(req, done, total, name),
                                 cancelled=self._cancel.is_set, completed=snap["completed"], treatment=snap["treatment"],
                                 theme=snap["theme"], custom_art=custom_art, **extra)
        except sc.SteamcaseError as e:
            error = str(e)
        except Exception as e:
            error = tr("Unexpected problem: %s") % e
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
        self._set_status(tr("%d of %d · %s") % (done, total, name if len(name) <= MAX_NAME else name[:MAX_NAME - 3] + "…"), "wait")

    def _on_made(self, req, res, error):
        if req != self._req:
            return
        self._set_state(running=False, making=False)
        if error:
            self._set_status(error, "error")
            self.failed.emit(tr("Could not make covers"), error)
            return
        self._save_groups(res)
        self._stopped = bool(res["cancelled"])
        if res["files"]:
            self._files = list(res["files"])
            self.doneChanged.emit()
            self._shell.setFact("covers_made", True)
        if not res["cancelled"]:                        # a stopped run leaves the bar where it stopped
            self._finished = self._total = max(self._total, self._finished)
            self.progressChanged.emit()
        self._set_status(*result_text(res, self._problems))

    def _save_groups(self, res):
        """After a run that made covers: the manual flow saves its groups (only the games that have a cover now) and lets go of the covers of deleted groups; the usual
        flow deletes the groups it repainted. Nothing is deleted before the covers exist, and a failed run never gets here."""
        snap = self._snap or {}
        made = {int(sc.appid_of(os.path.basename(f))) for f in res["files"] if sc.appid_of(os.path.basename(f)) is not None}
        try:
            if snap.get("manual"):
                saved = groups.drop_games(snap["save"], set(snap["platforms"]) - made)
                if snap["released"]:
                    sc.forget_group(self._covers, snap["released"])
                groups.save(self._covers, saved)
            elif snap.get("repaint"):
                done = {a for g in snap["repaint"] for a in g["games"]} & made
                groups.save(self._covers, groups.drop_games(groups.load(self._covers), done))
                self.groupsDeleted.emit(done)
        except OSError as e:
            self.failed.emit(tr("Could not save your groups"), tr("The covers are made, but your groups could not be saved: %s") % e)
        self._ticks.clear()
        self._ticks.refresh()

    @Slot()
    def cancel(self):
        if self._making and not self._cancel.is_set():
            self._cancel.set()
            self._set_status(tr("Stopping…"), "wait")

    @Slot()
    def openFolder(self):
        folder = os.path.abspath(self._covers)
        os.makedirs(folder, exist_ok=True)
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(folder)):
            self._set_status(tr("Could not open the folder. It is here: %s") % folder, "error")
            self.failed.emit(tr("Covers folder"), tr("Could not open the folder. It is here:\n\n%s") % folder)
