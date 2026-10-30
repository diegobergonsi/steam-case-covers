# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Step 5 of the window: adding the covers to Steam. Which account, whether Steam is running, the question before anything changes, and a worker
that closes Steam, copies the covers (with a backup) and starts Steam again. The words are those of the Tk window.
Restore and Reset live on Home and will use the same worker."""
import sys
import threading

from PySide6.QtCore import Property, QObject, Signal, Slot

import steamcase as sc

MAX_NAME = 28                               # a long account name must not push the buttons off the window
OPEN_NOTE = "Steam is open. Applying closes it: any running game stops and downloads pause. Save your game first."
CLOSED_NOTE = "Steam is closed, so nothing will be interrupted. Your current artwork is backed up first, so you can undo it."
CLOSE_WARNING = "Steam will be closed automatically. Any running game stops and downloads pause. Save your game first."


def _short(name):
    return name if len(name) <= MAX_NAME else name[:MAX_NAME - 1] + "…"


class Apply(QObject):
    steamChanged = Signal()
    accountChanged = Signal()
    restartChanged = Signal()
    canApplyChanged = Signal()              # busy, and whether there are covers to add
    statusChanged = Signal()
    appliedChanged = Signal()
    watchingChanged = Signal()
    confirmNeeded = Signal(str, list, str)  # the title, the paragraphs [{"text", "kind"}] and the label of the "yes" button
    _probed = Signal(bool)                  # whether Steam runs (from the probe thread)
    _stage = Signal(int, str)               # request, what the worker is doing now
    _finished = Signal(int, object, object)         # request, the words of the result, the words of the error

    def __init__(self, shell, make, covers_dir, parent=None):
        super().__init__(parent)
        self._shell = shell
        self._make = make
        self._covers = covers_dir
        self._steam_open, self._known = False, False
        self._watching, self._probing = False, False
        self._accounts, self._who, self._choice = [], "", None
        self._busy = self._asking = self._applied = False
        self._status, self._kind = "", "wait"
        self._req = 0
        self._probed.connect(self._on_probed)
        self._stage.connect(self._on_stage)
        self._finished.connect(self._on_finished)
        make.runningChanged.connect(self._make_changed)
        make.doneChanged.connect(self.canApplyChanged)
        self.refresh()

    # ----- Steam -----
    @Property(bool, notify=steamChanged)
    def steamOpen(self):
        return self._steam_open

    @Property(str, notify=steamChanged)
    def note(self):
        """The warning follows reality; until Steam has been asked it says nothing."""
        if not self._known:
            return ""
        return OPEN_NOTE if self._steam_open else CLOSED_NOTE

    @Property(str, notify=steamChanged)
    def noteKind(self):
        return "wait" if not self._known else "warn" if self._steam_open else "calm"

    def _get_watching(self):
        return self._watching

    def _set_watching(self, value):
        value = bool(value)
        if value != self._watching:
            self._watching = value
            self.watchingChanged.emit()
            if value:
                self._probe_start()

    watching = Property(bool, _get_watching, _set_watching, notify=watchingChanged)

    @Slot()
    def poll(self):
        """One question to the system whether Steam runs (call it every 1.5 s); only while the screen is shown."""
        if self._watching:
            self._probe_start()

    def _probe_start(self):
        if not self._probing:
            self._probing = True
            threading.Thread(target=self._probe, daemon=True).start()

    def _probe(self):
        """Off the UI thread: asking the system for its processes can take a moment."""
        running = sc.steam_running()
        try:
            self._probed.emit(bool(running))
        except RuntimeError:
            pass                                        # the window is closing

    def _on_probed(self, running):
        self._probing = False
        if (running, True) != (self._steam_open, self._known):
            self._steam_open, self._known = running, True
            self.steamChanged.emit()

    # ----- the account -----
    @Property("QVariantList", notify=accountChanged)
    def accounts(self):
        return list(self._accounts)

    @Property(str, notify=accountChanged)
    def accountId(self):
        return self._choice or ""

    @Property(str, notify=accountChanged)
    def accountLabel(self):
        return "Steam account: %s" % _short(self._who) if self._who else ""

    @Property(bool, notify=accountChanged)
    def canChoose(self):
        return len(self._accounts) > 1

    def _acc(self):
        """The account folder to use: the user's choice if it still exists, else None (the engine picks the one Steam used last)."""
        try:
            if self._choice and self._choice not in [a for a, _ in sc.list_accounts(sc.steam_dir())]:
                self._choice = None
                self.accountChanged.emit()
        except sc.SteamcaseError:
            self._choice = None
        return self._choice

    def accountChoice(self):
        """The account the user chose, checked again now, or None."""
        return self._acc()

    @Slot()
    def refresh(self):
        """Read which Steam accounts there are (call it when the screen opens)."""
        try:
            steam = sc.steam_dir()
            accounts = sc.list_accounts(steam)
            who = sc.account_label(steam, self._acc() or sc.pick_account(steam))
        except (sc.SteamcaseError, OSError):
            accounts, who = [], ""
        found = [{"key": a, "label": label} for a, label in accounts]
        if (found, who) != (self._accounts, self._who):
            self._accounts, self._who = found, who
            self.accountChanged.emit()

    @Slot(str)
    def chooseAccount(self, key):
        if self._busy or self._make.running or key not in [a["key"] for a in self._accounts]:
            return
        self._choice = key
        self._who = dict((a["key"], a["label"]) for a in self._accounts)[key]
        self.accountChanged.emit()
        self._set_status("", "wait")

    # ----- the switch -----
    def _get_restart(self):
        return self._shell.switchValue("restart_steam")

    def _set_restart(self, value):
        if bool(value) != self._get_restart():
            self._shell.setSwitch("restart_steam", bool(value))
            self.restartChanged.emit()

    restart = Property(bool, _get_restart, _set_restart, notify=restartChanged)

    # ----- state -----
    @Property(bool, notify=canApplyChanged)
    def busy(self):
        return self._busy

    @Property(bool, notify=canApplyChanged)
    def canApply(self):
        return not self._busy and self._make.done and not self._make.running

    @Property(bool, notify=appliedChanged)
    def applied(self):
        return self._applied

    @Property(str, notify=statusChanged)
    def status(self):
        return self._status

    @Property(str, notify=statusChanged)
    def statusKind(self):
        return self._kind

    def _set_status(self, text, kind):
        if (text, kind) != (self._status, self._kind):
            self._status, self._kind = text, kind
            self.statusChanged.emit()

    def _set_applied(self, value):
        if value != self._applied:
            self._applied = value
            self.appliedChanged.emit()
            self._shell.setFact("applied", value)

    def _make_changed(self):
        self.canApplyChanged.emit()
        if self._make.running and (self._applied or self._status):
            self._set_applied(False)                    # new covers are coming: what was said about the old ones is no longer true
            self._set_status("", "wait")

    # ----- apply -----
    @Slot()
    def apply(self):
        """Ask first: nothing changes until the user says yes."""
        if self._asking or not self.canApply:
            return
        try:
            steam = sc.steam_dir()
            who = sc.account_label(steam, sc.pick_account(steam, self._acc()))
        except sc.SteamcaseError:
            who = "your Steam account"
        paragraphs = [{"text": "%d covers will be added to the Steam account “%s”." % (len(self._make.files()), who), "kind": "main"},
                      {"text": "Your current artwork is backed up first. You can undo this from the Home screen.", "kind": "muted"}]
        if self._steam_open:
            paragraphs.append({"text": CLOSE_WARNING, "kind": "warn"})
        self._asking = True
        self.confirmNeeded.emit("Add covers to Steam", paragraphs, "Close Steam and add them" if self._steam_open else "Add them")

    @Slot()
    def decline(self):
        self._asking = False

    @Slot()
    def confirm(self):
        if not self._asking:
            return
        self._asking = False
        self._busy = True
        self.canApplyChanged.emit()
        self._req += 1
        self._set_status("Closing Steam…" if self._steam_open else "Working…", "wait")
        job = {"restart": self.restart, "account": self._acc(), "files": self._make.files()}
        threading.Thread(target=self._work, args=(self._req, job), daemon=True).start()

    def _work(self, req, job):
        """Off the UI thread: close Steam if it runs, copy the covers, start Steam again if asked. Talks to the window only through signals."""
        def say(text):
            try:
                self._stage.emit(req, text)
            except RuntimeError:
                pass
        text = error = None
        try:
            steam = sc.steam_dir()
            if sc.steam_running():
                say("Closing Steam…")
                if not sc.close_steam(steam):
                    raise sc.SteamcaseError("Steam did not close in time. Close it yourself (Steam menu, then Exit) and press the button again."
                                            + (" If macOS asked for permission, allow it first and then press the button again." if sys.platform == "darwin" else ""))
            say("Backing up and copying covers…")
            r = sc.apply_covers(steam, self._covers, job["account"], files=job["files"])
            if r["applied"]:
                text = "Done. %d covers added to the Steam account “%s” (%d replaced older art, %d already up to date). Backup saved in: %s" % (
                    r["applied"], r["account_name"], r["replaced"], r["unchanged"], r["backup"])
                if r["jpg_moved"]:
                    text += " Art you had set by hand in Steam (%d games) was moved into the backup; Restore brings it back." % r["jpg_moved"]
            else:
                text = "Nothing to change: all %d covers were already in the Steam account “%s”." % (r["unchanged"], r["account_name"])
            if job["restart"]:
                say("Starting Steam…")
                try:
                    sc.start_steam(steam)
                    text += " Steam is starting."
                except sc.SteamcaseError as e:
                    text += " Could not start Steam (%s). Please open it yourself." % e
            else:
                text += " Start Steam to see the change."
        except sc.SteamcaseError as e:
            error = str(e)
        except Exception as e:                          # never leave the window stuck in "busy"
            error = "Unexpected problem: %s" % e
        try:
            self._finished.emit(req, text, error)
        except RuntimeError:
            pass

    def _on_stage(self, req, text):
        if req == self._req and self._busy:
            self._set_status(text, "wait")

    def _on_finished(self, req, text, error):
        if req != self._req:
            return
        self._busy = False
        self.canApplyChanged.emit()
        if error:
            self._set_status(error, "error")
        else:
            self._set_status(text, "ok")
            self._set_applied(True)
