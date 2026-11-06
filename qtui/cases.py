# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""The Case step of the manual flow: which case the ticked games go in, as a named group (a console case, or the Steam case in a colour or gold). The choices are
kept per game until Make; the covers themselves (and the 100% marks, which have their own step) are made by Make, which also saves the groups (groups.py)."""
from PySide6.QtCore import Property, QObject, Signal, Slot

from engine import groups
from engine import steamcase as sc
from qtui import tones
from qtui.i18n import N_, tr, trn

ORDER = ("steam", "ps5", "ps4", "ps3", "xboxseries", "xboxone", "xbox360", "switch2", "switch", sc.CUSTOM)       # the Steam case first, then newest to oldest, then the user's own
LABELS = dict(sc.PLATFORM_LABELS, steam="Steam", custom=N_("My own case"))      # shown through tr(): the brand names have no translation and stay as they are


def _colour_choices():
    """The nine ready-made colours of the Look step: [{"label", "color", "hue", "sat", "val"}]. The first is named Blue, and the orange one Gold: it is the colour of the
    gold case (sc.GOLD_HUE is one of the hues of the swatches)."""
    names = {(0, 100, 100): tr("Blue"), (sc.GOLD_HUE, 100, 100): tr("Gold")}
    return [dict(label=names.get((x["hue"], x["sat"], x["val"]), x["name"]), color=x["color"], hue=x["hue"], sat=x["sat"], val=x["val"]) for x in tones.swatches()]




def games_line(label, count):
    """"PlayStation 5 · 3 games": a case and how many games are in it."""
    return label + " \u00b7 " + trn("%n game|%n games", count)


def group_caption(name, label, count):
    """The line that names a group in a list: its name, its case (left out when the name already says it) and how many games."""
    return " \u00b7 ".join([name] + ([label] if label and label != name else []) + [trn("%n game|%n games", count)])


def case_label(case):
    """How a group's case is named: a console's name, or "Steam case, red" for the Steam case in a colour (a group's "case" as groups.py keeps it)."""
    if "platform" in case:
        return tr(LABELS.get(case["platform"], ""))
    tone = tuple(case["tone"])
    found = next((c["label"] for c in _colour_choices() if sc.tone_key(c["hue"], c["sat"], c["val"]) == sc.tone_key(*tone)), tr("custom colour"))
    return tr("Steam case, ") + found.lower()


class Cases(QObject):
    selectedKeyChanged = Signal()
    assignmentsChanged = Signal()
    familyChanged = Signal()
    availabilityChanged = Signal()
    groupsChanged = Signal()
    groupNameChanged = Signal()
    colourChanged = Signal()
    errorChanged = Signal()
    choicesChanged = Signal()
    previewChanged = Signal()               # the choice, what is in use, or the own case changed

    def __init__(self, shell, parent=None, covers_dir=None):
        super().__init__(parent)
        self._shell = shell
        self._covers = covers_dir or sc.default_covers_dir()
        self._key = ""
        self._assigned = {}                 # appid -> a platform of sc.PLATFORMS, or None for the Steam case
        self._tones = {}                    # appid -> (hue, sat, val), for the games of this run in the Steam case
        self._gids = {}                     # appid -> id of the group the game was put in during this run
        self._groups = groups.load(self._covers)       # the working list: the saved groups and this run's changes (saved by Make)
        self._deleted = []                  # the groups deleted in this run
        self._gid = ""                      # the saved group picked, or "" for a new one
        self._tone = (0, 100, 100)
        self._name, self._typed, self._error = "", False, ""
        self._family = False
        for signal in (self.selectedKeyChanged, self.assignmentsChanged, self.choicesChanged):
            signal.connect(self.previewChanged)
        shell.owncase.changed.connect(self.choicesChanged)         # the card of the user's own case shows the case, or asks for a file
        shell.picker.selectionChanged.connect(self.selectedKeyChanged)           # canAssign follows the ticks too
        self._library_seen = self._library_state()
        shell.library.pathChanged.connect(self._library_changed)
        shell.library.installedOnlyChanged.connect(self._library_changed)

    @Property("QVariantList", notify=choicesChanged)
    def choices(self):
        """The cards of the Case step: {"key", "label", "source" (the picture of the case), "ask" (true for "My own case" while there is no file to show)}."""
        own = self._shell.owncase
        return [{"key": k, "label": tr(LABELS[k]), "ask": k == sc.CUSTOM and not own.available,
                 "source": "image://preview/platform/%s/%d" % (k, own.serial if k == sc.CUSTOM else 1)} for k in ORDER]

    @Property(str, notify=selectedKeyChanged)
    def selectedKey(self):
        return self._key

    @Property(str, notify=selectedKeyChanged)
    def selectedLabel(self):
        """How the case picked is named ("PlayStation 5", "Steam case, red"), or "" when none is."""
        return self._case_label(self._key, self._tone) if self._key else ""

    @Slot(str)
    def pick(self, key):
        """Pick a case for a new group."""
        if key == sc.CUSTOM:                # always asks for the file: picking again replaces the case
            self._shell.owncase.ask(self._pick_custom)
            return
        if key in ORDER and key != self._key:
            self._new_group(key)

    @Slot()
    def newGroup(self):
        """The "New group" card: leave the saved group and keep its case for a new one, with no message and without asking for the own case file."""
        if self._gid:
            self._gid = ""
            self._follow_case()
            self.selectedKeyChanged.emit()

    def _pick_custom(self):
        self._new_group(sc.CUSTOM)

    def _new_group(self, key):
        """A case was picked: a new group starts with it. Leaving a saved group is said in a toast."""
        left = self._gid != ""
        self._key, self._gid = key, ""
        self._follow_case()
        self.selectedKeyChanged.emit()
        if left:
            self._shell.toast.emit(tr("You picked a new case, so the saved group was unselected."))

    # ----- the colour of the Steam case, the name and the groups -----
    @Property("QVariantList", constant=True)
    def colourChoices(self):
        return _colour_choices()

    @Property(int, notify=colourChanged)
    def colourIndex(self):
        """The index in colourChoices of the colour picked, or -1 (a saved group in a colour the list does not have)."""
        return next((i for i, c in enumerate(_colour_choices()) if sc.tone_key(c["hue"], c["sat"], c["val"]) == sc.tone_key(*self._tone)), -1)

    @Slot(int)
    def pickColour(self, index):
        colours = _colour_choices()
        if 0 <= index < len(colours):
            c = colours[index]
            self._tone, self._gid = (c["hue"], c["sat"], c["val"]), ""
            self._follow_case()
            self.colourChanged.emit()
            self.selectedKeyChanged.emit()

    def _case_label(self, key, tone):
        return case_label({"tone": list(tone)} if key == "steam" else {"platform": key})

    def _follow_case(self):
        """A group not named by the user is named after its case."""
        if not self._typed and not self._gid:
            self._name = self._case_label(self._key, self._tone) if self._key else ""
        self.groupNameChanged.emit()
        self.colourChanged.emit()

    def _get_name(self):
        group = next((g for g in self._groups if g["id"] == self._gid), None)
        return group["name"] if group else self._name

    def _set_name(self, value):
        if not self._gid and value != self._name:
            self._name, self._typed = str(value), True
            self._set_error("")
            self.groupNameChanged.emit()

    groupName = Property(str, _get_name, _set_name, notify=groupNameChanged)

    @Property(str, notify=errorChanged)
    def error(self):
        return self._error

    def _set_error(self, text):
        if text != self._error:
            self._error = text
            self.errorChanged.emit()

    @Property(str, notify=selectedKeyChanged)
    def selectedGroup(self):
        return self._gid

    @Property("QVariantList", notify=groupsChanged)
    def groupList(self):
        """The groups, saved ones and this run's, as the cards of the Case step read them: {"id", "name", "count", "subtitle" (its case and games)}."""
        return [{"id": g["id"], "name": g["name"], "count": len(g["games"]), "subtitle": games_line(case_label(g["case"]), len(g["games"]))} for g in self._groups]

    @Slot(str)
    def pickGroup(self, group_id):
        """Pick a saved group: its games get its case, whatever else is picked."""
        group = next((g for g in self._groups if g["id"] == group_id), None)
        if group is None:
            return
        case = group["case"]
        self._gid = group_id
        self._key = "steam" if "tone" in case else case["platform"]
        if "tone" in case:
            self._tone = tuple(case["tone"])
        self._set_error("")
        self.groupNameChanged.emit()
        self.colourChanged.emit()
        self.selectedKeyChanged.emit()

    @Slot(str)
    def deleteGroup(self, group_id):
        """Take a group out of the list (Make saves that): its games of this run lose their case, the others are released at Make."""
        group = next((g for g in self._groups if g["id"] == group_id), None)
        if group is None:
            return
        self._groups = [g for g in self._groups if g["id"] != group_id]
        self._deleted.append(group)
        for appid in [a for a, gid in self._gids.items() if gid == group_id]:
            for d in (self._assigned, self._tones, self._gids):
                d.pop(appid, None)
        if self._gid == group_id:
            self._gid, self._key = "", ""
            self.selectedKeyChanged.emit()
            self.groupNameChanged.emit()
        self.groupsChanged.emit()
        self.assignmentsChanged.emit()

    def released(self):
        """The games of the groups deleted in this run that are in no group now: their covers, if they have one, lose the group note."""
        kept = {a for g in self._groups for a in g["games"]}
        return {a for g in self._deleted for a in g["games"]} - kept

    def groupsToSave(self):
        """The groups as Make saves them: the saved ones and this run's changes."""
        return [dict(g, games=list(g["games"])) for g in self._groups]

    @Slot()
    def reloadGroups(self):
        self._groups, self._deleted = groups.load(self._covers), []
        if self._gid and not any(g["id"] == self._gid for g in self._groups):
            self._gid, self._key = "", ""
            self.selectedKeyChanged.emit()
        self.groupsChanged.emit()
        self.groupNameChanged.emit()

    @Property(bool, notify=selectedKeyChanged)
    def canAssign(self):
        return bool(self._key) and self._shell.picker.selectedCount > 0

    @Slot()
    def assign(self):
        """Put the ticked games in the picked case; they are then unticked, so the next round starts clean."""
        if not self.canAssign:
            return
        games = self._shell.picker.selection()
        group = next((g for g in self._groups if g["id"] == self._gid), None)
        case = group["case"] if group else ({"tone": list(self._tone)} if self._key == "steam" else {"platform": self._key})
        try:
            self._groups, gid = groups.assign(self._groups, group["name"] if group else self._name, case, games)
        except ValueError as e:
            self._set_error(str(e))
            return
        for appid in games:
            self._assigned[appid] = None if self._key == "steam" else self._key
            if self._key == "steam":
                self._tones[appid] = tuple(case["tone"])
            else:
                self._tones.pop(appid, None)
            self._gids[appid] = gid
        self._key, self._gid, self._name, self._typed, self._tone = "", "", "", False, (0, 100, 100)
        self._set_error("")
        self.groupsChanged.emit()
        self.assignmentsChanged.emit()              # first: the games count as given a case before the ticks go, or the Case step would look locked for a moment
        self._shell.picker.untick(games)
        self.selectedKeyChanged.emit()
        self.groupNameChanged.emit()
        self.colourChanged.emit()

    def assigned(self):
        """{appid: platform or None (the Steam case)} for make_covers."""
        return dict(self._assigned)

    def tones(self):
        """{appid: (hue, sat, val)} of the games of this run in the Steam case, for make_covers."""
        return dict(self._tones)

    def groupIds(self):
        """{appid: group id} of the games of this run, for make_covers."""
        return dict(self._gids)

    @Property(int, notify=assignmentsChanged)
    def assignedCount(self):
        return len(self._assigned)

    @Property("QVariantList", notify=assignmentsChanged)
    def summary(self):
        """{"key", "label", "count"} for every case in use, in the order of the choices."""
        used = list(self._assigned.values())
        return [{"key": k, "label": tr(LABELS[k]), "count": used.count(None if k == "steam" else k)} for k in ORDER if (None if k == "steam" else k) in used]

    @Property(str, notify=assignmentsChanged)
    def soFar(self):
        """The cases in use, as one line for the Case step: "So far: PlayStation 5 · 3 games, Xbox One · 1 game" (empty until a game has a case)."""
        if not self.summary:
            return ""
        return tr("So far: %s") % ", ".join(games_line(s["label"], s["count"]) for s in self.summary)

    @Property(str, notify=previewChanged)
    def previewSource(self):
        """The sample cover beside the choices: the case picked, else the one most games are in, else the Steam case."""
        key = self._key or self.previewKey or "steam"
        return next(c["source"] for c in self.choices if c["key"] == key)

    @Property(str, notify=assignmentsChanged)
    def previewKey(self):
        """The case most games are in (the first one on a tie): the sample shown on the Make screen."""
        top = max(self.summary, key=lambda s: s["count"], default=None)
        return top["key"] if top else ""

    def _get_family(self):
        return self._family

    def _set_family(self, value):
        value = bool(value)
        if value != self._family:
            self._family = value
            self.familyChanged.emit()

    family = Property(bool, _get_family, _set_family, notify=familyChanged)

    @Property(bool, notify=availabilityChanged)
    def familyAvailable(self):
        """Family games are only known from a game list file (an installed-only run knows nothing about ownership)."""
        library = self._shell.library
        return (not library.installedOnly) and bool(library.path)

    def _library_state(self):
        library = self._shell.library
        return (library.path, bool(library.installedOnly))

    def _library_changed(self):
        state = self._library_state()
        if state == self._library_seen:             # told again (a change of language does that to every property): the list is the same
            return
        self._library_seen = state
        self.availabilityChanged.emit()
        if self._assigned:                  # the games belong to the old list
            self._assigned, self._tones, self._gids = {}, {}, {}
            self.assignmentsChanged.emit()

    @Slot()
    def reset(self):
        self._key, self._assigned, self._family = "", {}, False
        self._tones, self._gids, self._gid, self._name, self._typed, self._tone = {}, {}, "", "", False, (0, 100, 100)
        self._set_error("")
        self.reloadGroups()
        self.selectedKeyChanged.emit()
        self.assignmentsChanged.emit()
        self.familyChanged.emit()
        self.groupNameChanged.emit()
        self.colourChanged.emit()
