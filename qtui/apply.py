# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Step 5 of the window: adding the covers to Steam. Which account, whether Steam is running, the question before anything changes, and a worker
that closes Steam, copies the covers (with a backup) and starts Steam again. The words are those of the Tk window.
Restore and Reset live on Home and will use the same worker."""
import os
import sys
import threading

from PySide6.QtCore import Property, QObject, Signal, Slot

import steamcase as sc

MAX_NAME = 28                               # a long account name must not push the buttons off the window
OPEN_NOTE = "Steam is open. Changing the artwork closes it: any running game stops and downloads pause. Save your game first."
CHECKING_NOTE = "Checking whether Steam is open\u2026"
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
    failed = Signal(str)                    # the words of an error, for a box the user cannot miss wherever they are
    undoChanged = Signal()                  # whether there is anything to restore or reset
    confirmNeeded = Signal(str, list, str, str)     # the title, the paragraphs [{"text", "kind"}], the label of the "yes" button and of a second way forward ("": none)
    _probed = Signal(bool)                  # whether Steam runs (from the probe thread)
    _stage = Signal(int, str)               # request, what the worker is doing now
    _finished = Signal(int, object, object)         # request, the words of the result, the words of the error
    _undone = Signal(bool, bool, object)            # is there a backup, is there art of ours to reset, for which account (from the probe thread)
    _scanned = Signal(int, object, object, int, object)     # request, our covers, the account's name, other custom art, the words of an error

    def __init__(self, shell, make, covers_dir, parent=None):
        super().__init__(parent)
        self._shell = shell
        self._make = make
        self._covers = covers_dir
        self._steam_open, self._known = False, False
        self._watching, self._probing = False, False
        self._accounts, self._who, self._choice = [], "", None
        self._raw = {}                                  # folder id -> the name as Steam knows it
        self._busy = self._asking = self._applied = False
        self._pending = None                            # (mode, names) waiting for the answer to the question
        self._mode = "apply"
        self._backup = self._art = self._undo_known = self._undoing = self._again = False
        self._status, self._kind = "", "wait"
        self._req = 0
        self._probed.connect(self._on_probed)
        self._stage.connect(self._on_stage)
        self._finished.connect(self._on_finished)
        self._undone.connect(self._on_undone)
        self._scanned.connect(self._on_scanned)
        make.runningChanged.connect(self._make_changed)
        make.doneChanged.connect(self.canApplyChanged)
        make.doneChanged.connect(self.undoChanged)       # the accounts are read when the screen opens (refresh), not at start-up

    # ----- Steam -----
    @Property(bool, notify=steamChanged)
    def steamOpen(self):
        return self._steam_open

    @Property(str, notify=steamChanged)
    def note(self):
        """The warning follows reality; until Steam has been asked it says so, and takes the space the answer will need."""
        if not self._known:
            return CHECKING_NOTE
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
                self.refreshUndo()

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
                self.refresh()                          # the label follows: it must name the account that will really be used
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
        found = [{"key": a, "label": _short("Account %s" % label if label.isdigit() else label)} for a, label in accounts]
        self._raw = dict(accounts)
        if (found, who) != (self._accounts, self._who):
            self._accounts, self._who = found, who
            self.accountChanged.emit()

    @Slot(str)
    def chooseAccount(self, key):
        if self._busy or self._make.running or key not in [a["key"] for a in self._accounts]:
            return
        self._choice = key
        self._who = self._raw.get(key, key)
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

    @Property(str, notify=canApplyChanged)
    def readyText(self):
        n = len(self._make.files())
        return "No covers yet. Make them first." if n == 0 else "1 cover is ready to add." if n == 1 else "%d covers are ready to add." % n

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
        self.undoChanged.emit()
        if self._make.canCancel and (self._applied or self._status):         # only when covers are really being made, not when a question is asked
            self._set_applied(False)                    # new covers are coming: what was said about the old ones is no longer true
            self._set_status("", "wait")

    # ----- undo: what can be restored or reset (probed off the UI thread when the screen opens and after every job) -----
    @Property(bool, notify=undoChanged)
    def undoKnown(self):
        return self._undo_known

    def _idle(self):
        return not self._busy and not self._asking and not self._make.running

    @Property(bool, notify=undoChanged)
    def asking(self):
        return self._asking

    @Property(bool, notify=undoChanged)
    def canRestore(self):
        return self._idle() and self._backup

    @Property(bool, notify=undoChanged)
    def canReset(self):
        return self._idle() and self._art

    @Property(str, notify=undoChanged)
    def undoHint(self):
        """Why Restore is greyed out; gone as soon as there is something to say instead."""
        if self._undo_known and not self._backup and not self._status and self._idle() and not self.canApply:
            return "Nothing to undo yet: \u201cRestore previous artwork\u201d works once you have used \u201cApply to Steam\u201d in this app."
        return ""

    @Slot()
    def refreshUndo(self):
        if self._undoing:
            self._again = True                          # something changed while a look was running: look again when it returns
            return
        self._undoing = True
        threading.Thread(target=self._undo_probe, args=(self._acc(),), daemon=True).start()

    def _undo_probe(self, account):
        """Off the UI thread: looking in Steam's folders."""
        backup = art = False
        try:
            steam = sc.steam_dir()
            backup = bool(sc.list_backups(steam, account))
            grid = sc.grid_dir(steam, account)
            art = os.path.isdir(grid) and any(sc._COVER_NAME.match(n) or sc._JPG_NAME.match(n) for n in os.listdir(grid))
        except (sc.SteamcaseError, OSError):
            pass
        try:
            self._undone.emit(backup, art, account)
        except RuntimeError:
            pass

    def _on_undone(self, backup, art, account):
        self._undoing = False
        if self._again or account != self._choice:        # the answer is already out of date
            self._again = False
            self.refreshUndo()
            return
        self._undo_known = True
        self._backup, self._art = backup, art
        self.undoChanged.emit()

    # ----- the questions -----
    def _who_is(self):
        try:
            steam = sc.steam_dir()
            return sc.account_label(steam, sc.pick_account(steam, self._acc()))
        except sc.SteamcaseError:
            return "your Steam account"

    def _ask(self, mode, title, paragraphs, go, alt="", names=None):
        if self._steam_open:
            paragraphs.append({"text": CLOSE_WARNING, "kind": "warn"})
        self._pending = (mode, names)
        self._asking = True
        self.undoChanged.emit()
        self.confirmNeeded.emit(title, paragraphs, go, alt)

    @Slot()
    def apply(self):
        """Ask first: nothing changes until the user says yes."""
        if self._asking or not self.canApply:
            return
        self._ask("apply", "Add covers to Steam",
                  [{"text": "%d covers will be added to the Steam account \u201c%s\u201d." % (len(self._make.files()), self._who_is()), "kind": "main"},
                   {"text": "Your current artwork is backed up first. You can undo this from the Home screen.", "kind": "muted"}],
                  "Close Steam and add them" if self._steam_open else "Add them")

    @Slot()
    def restore(self):
        if self._asking or not self.canRestore:
            return
        self._ask("restore", "Restore previous artwork",
                  [{"text": "Your artwork from before the last Apply will be put back on the Steam account \u201c%s\u201d." % self._who_is(), "kind": "main"},
                   {"text": "The covers added by that Apply are removed.", "kind": "muted"}],
                  "Close Steam and restore" if self._steam_open else "Restore")

    @Slot()
    def reset(self):
        """Step 1 of 2: look for our covers (a few seconds, in the background). Step 2 asks, then removes them."""
        if self._asking or not self.canReset:
            return
        self._busy = True
        self.canApplyChanged.emit()
        self.undoChanged.emit()
        self._req += 1
        self._set_status("Looking for covers made by this app\u2026 (a few seconds)", "wait")
        threading.Thread(target=self._scan_worker, args=(self._req, self._acc()), daemon=True).start()

    def _scan_worker(self, req, account):
        names = who = error = None
        other = 0
        try:
            steam = sc.steam_dir()
            names = sc.find_our_covers(steam, account, progress=lambda i, n: self._tell(req, "Checking Steam's artwork\u2026 %d of %d" % (i, n)),
                                       cancelled=lambda: req != self._req)
            who = sc.account_label(steam, sc.pick_account(steam, account))
            extra, others = sc.find_other_art(steam, account, names)
            other = len(extra) + len(others)
        except sc.SteamcaseError as e:
            error = str(e)
        except Exception as e:
            error = "Unexpected problem: %s" % e
        try:
            self._scanned.emit(req, names, who, other, error)
        except RuntimeError:
            pass

    def _tell(self, req, text):
        try:
            self._stage.emit(req, text)
        except RuntimeError:
            pass

    def _on_scanned(self, req, names, who, other, error):
        if req != self._req:
            return
        if error:
            self._busy = False
            self._set_status(error, "error")
            self.canApplyChanged.emit()
            self.undoChanged.emit()
            self.failed.emit(error)
            return
        if not names and not other:
            self._busy = False
            self._set_status("No custom covers were found in \u201c%s\u201d. Nothing to reset." % who, "wait")
            self.canApplyChanged.emit()
            self.undoChanged.emit()
            return
        paragraphs = []
        if names:
            paragraphs.append({"text": "%d covers made by this app will be removed from the Steam account \u201c%s\u201d. Steam goes back to its own default art for them." % (len(names), who), "kind": "main"})
        if other:
            paragraphs.append({"text": "Found %d more custom covers that this app did not make (from SteamGridDB or set by hand in Steam)." % other, "kind": "main"})
        paragraphs.append({"text": "A backup is kept, so \u201cRestore previous artwork\u201d brings everything back.", "kind": "muted"})
        close = "Close Steam and " if self._steam_open else ""
        if other and names:
            go, alt = (close + "remove only ours") if close else "Remove only ours", (close + "remove all") if close else "Remove all"
        elif other:
            go, alt = (close + "remove all") if close else "Remove all", ""
        else:
            go, alt = "Close Steam and reset" if close else "Reset", ""
        self._ask("reset", "Reset to Steam's default art", paragraphs, go, alt, {"names": names, "everything": not names})

    @Slot()
    def decline(self):
        if self._asking and self._pending and self._pending[0] == "reset":
            self._busy = False
            self._set_status("", "wait")
            self.canApplyChanged.emit()
        self._asking = False
        self._pending = None
        self.undoChanged.emit()

    @Slot()
    def confirm(self):
        self._go(False)

    @Slot()
    def confirmAlternate(self):
        self._go(True)

    def _go(self, alternate):
        if not self._asking or not self._pending:
            return
        mode, names = self._pending
        self._pending, self._asking = None, False
        self._busy = True
        self._mode = mode
        self.canApplyChanged.emit()
        self.undoChanged.emit()
        self._req += 1
        self._set_status("Closing Steam\u2026" if self._steam_open else "Working\u2026", "wait")
        job = {"mode": mode, "restart": self.restart, "account": self._acc(), "files": self._make.files() if mode == "apply" else [],
               "names": (names or {}).get("names"), "everything": True if alternate else (names or {}).get("everything", False)}
        threading.Thread(target=self._work, args=(self._req, job), daemon=True).start()

    def _work(self, req, job):
        """Off the UI thread: close Steam if it runs, do the job, start Steam again if asked. Talks to the window only through signals."""
        say = lambda text: self._tell(req, text)
        text = error = None
        try:
            steam = sc.steam_dir()
            if sc.steam_running():
                say("Closing Steam\u2026")
                if not sc.close_steam(steam):
                    raise sc.SteamcaseError("Steam did not close in time. Close it yourself (Steam menu, then Exit) and press the button again."
                                            + (" If macOS asked for permission, allow it first and then press the button again." if sys.platform == "darwin" else ""))
            if job["mode"] == "apply":
                say("Backing up and copying covers\u2026")
                r = sc.apply_covers(steam, self._covers, job["account"], files=job["files"])
                if r["applied"]:
                    text = "Done. %d covers added to the Steam account \u201c%s\u201d (%d replaced older art, %d already up to date). Backup saved in: %s" % (
                        r["applied"], r["account_name"], r["replaced"], r["unchanged"], r["backup"])
                    if r["jpg_moved"]:
                        text += " Art you had set by hand in Steam (%d games) was moved into the backup; Restore brings it back." % r["jpg_moved"]
                else:
                    text = "Nothing to change: all %d covers were already in the Steam account \u201c%s\u201d." % (r["unchanged"], r["account_name"])
            elif job["mode"] == "reset":
                say("Removing our covers\u2026")
                r = sc.reset_to_default(steam, job["account"], job["names"], job["everything"])
                text = "Done. %d covers removed from the Steam account \u201c%s\u201d: Steam shows its own default art again. Press \u201cRestore previous artwork\u201d to bring them back." % (
                    r["removed"], r["account_name"])
            else:
                backups = sc.list_backups(steam, job["account"])
                if not backups:
                    raise sc.SteamcaseError("No backup found.")
                n = sc.restore_backup(steam, backups[0], job["account"])
                left = len(sc.list_backups(steam, job["account"]))
                text = "Restored your previous artwork (%d files)." % n
                if left:
                    text += " %d older backup%s left: press Restore again to go one step further back." % (left, "" if left == 1 else "s")
            if job["restart"]:
                say("Starting Steam\u2026")
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
        self.undoChanged.emit()
        if error:
            self._set_status(error, "error")
            self.failed.emit(error)
        else:
            self._set_status(text, "ok")
            self._set_applied(self._mode == "apply")         # a restore or a reset undoes what was applied
        self.refreshUndo()
