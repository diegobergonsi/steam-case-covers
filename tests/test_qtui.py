# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Tests of the Qt window (the qtui package). The parts that need Qt skip themselves when PySide6 is missing.
Run:  python -m unittest discover -s tests -v   (with Qt: QT_QPA_PLATFORM=offscreen QT_QUICK_CONTROLS_STYLE=Basic python -m unittest tests.test_qtui)"""
import json, os, shutil, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from qtui import settings as st
from qtui import steps as sp

try:
    from PySide6.QtCore import QCoreApplication
except ImportError:
    QCoreApplication = None
need_qt = unittest.skipIf(QCoreApplication is None, "PySide6 missing")


class Settings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.path = os.path.join(self.tmp, "steamcase", "settings.json")

    def test_missing_file_gives_defaults(self):
        got = st.load_settings(self.path)
        self.assertEqual(got, st.DEFAULTS)
        self.assertEqual(tuple(got), st.SETTING_KEYS)

    def test_defaults_are_the_agreed_ones(self):
        self.assertEqual(st.DEFAULTS, {"skip_auto_art": False, "use_custom_art": False, "installed_only": False, "restart_steam": True, "reduce_effects": False})

    def test_save_then_load_roundtrip(self):
        values = dict(st.DEFAULTS, skip_auto_art=True, restart_steam=False, reduce_effects=True)
        self.assertTrue(st.save_settings(values, self.path))
        self.assertEqual(st.load_settings(self.path), values)

    def test_garbage_gives_defaults(self):
        os.makedirs(os.path.dirname(self.path))
        for blob in (b"", b"not json", b"[1, 2]", b'"text"', b"null", b"\xff\xfe\x00", b"{" * 5000, b" " * (5 * 1024 * 1024)):
            with self.subTest(blob[:12]):
                with open(self.path, "wb") as f:
                    f.write(blob)
                self.assertEqual(st.load_settings(self.path), st.DEFAULTS)

    def test_a_value_that_is_not_a_bool_falls_back_for_that_key_only(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "w") as f:
            json.dump({"skip_auto_art": "yes", "use_custom_art": 1, "installed_only": True, "restart_steam": None, "reduce_effects": True}, f)
        self.assertEqual(st.load_settings(self.path), dict(st.DEFAULTS, installed_only=True, reduce_effects=True))

    def test_unknown_keys_are_dropped_and_never_written(self):
        st.save_settings({"account": "111", "path": "/home/x", "reduce_effects": True}, self.path)
        with open(self.path) as f:
            self.assertEqual(list(json.load(f)), list(st.SETTING_KEYS))
        self.assertTrue(st.load_settings(self.path)["reduce_effects"])

    def test_save_is_atomic_and_leaves_no_temp_file(self):
        st.save_settings(st.DEFAULTS, self.path)
        st.save_settings(dict(st.DEFAULTS, reduce_effects=True), self.path)
        self.assertEqual(os.listdir(os.path.dirname(self.path)), ["settings.json"])

    def test_unwritable_place_returns_false_and_does_not_raise(self):
        blocker = os.path.join(self.tmp, "file")
        with open(blocker, "w") as f:
            f.write("x")
        self.assertFalse(st.save_settings(st.DEFAULTS, os.path.join(blocker, "settings.json")))       # a file where the folder should be

    def test_the_default_path_sits_next_to_the_covers_folder(self):
        import steamcase as sc
        self.assertEqual(os.path.dirname(st.settings_path()), os.path.dirname(sc.default_covers_dir()))
        self.assertEqual(os.path.basename(st.settings_path()), "settings.json")


class StepStates(unittest.TestCase):
    def states(self, **facts):
        return sp.step_states(**dict(dict(ready=False, look_done=False, hundred_done=False, covers_made=False, applied=False), **facts))

    def test_the_steps_and_their_labels(self):
        self.assertEqual(sp.STEPS, ("home", "game_list", "look", "hundred", "make", "add"))
        self.assertEqual([sp.LABELS[k] for k in sp.STEPS], ["Home", "1  Game list", "2  Look", "3  100% games", "4  Make", "5  Add to Steam"])

    def test_nothing_done_only_the_game_list_is_active(self):
        self.assertEqual(self.states(), {"home": "open", "game_list": "active", "look": "locked", "hundred": "locked", "make": "locked", "add": "locked"})

    def test_each_fact_moves_the_active_step_one_on(self):
        order = [("ready", "look"), ("look_done", "hundred"), ("hundred_done", "make"), ("covers_made", "add")]
        facts = {}
        for fact, active in order:
            facts[fact] = True
            got = self.states(**facts)
            self.assertEqual([k for k, v in got.items() if v == "active"], [active], fact)

    def test_everything_done(self):
        got = self.states(ready=True, look_done=True, hundred_done=True, covers_made=True, applied=True)
        self.assertEqual(got, {"home": "open", "game_list": "done", "look": "done", "hundred": "done", "make": "done", "add": "done"})

    def test_an_inconsistent_state_never_unlocks_a_later_step(self):
        self.assertEqual(self.states(covers_made=True)["make"], "locked")                     # covers but no game list
        self.assertEqual(self.states(hundred_done=True)["hundred"], "locked")                 # hundred done, look not
        got = self.states(ready=True, applied=True)
        self.assertEqual((got["look"], got["add"]), ("active", "locked"))


@need_qt
class ShellObject(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        from qtui.shell import Shell
        self.Shell = Shell
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.path = os.path.join(self.tmp, "settings.json")
        self.shell = Shell(self.path)

    def states(self):
        return {s["key"]: s["state"] for s in self.shell.steps}

    def test_starts_on_home_with_the_game_list_active(self):
        self.assertEqual(self.shell.current, 0)
        self.assertEqual(self.states()["game_list"], "active")
        self.assertEqual([s["label"] for s in self.shell.steps], [sp.LABELS[k] for k in sp.STEPS])

    def test_a_locked_step_cannot_be_reached(self):
        self.shell.go(2)
        self.assertEqual(self.shell.current, 0)

    def test_after_the_game_list_is_ready_look_opens(self):
        self.shell.setFact("ready", True)
        self.shell.go(2)
        self.assertEqual(self.shell.current, 2)
        self.assertEqual(self.states()["look"], "active")

    def test_out_of_range_is_ignored(self):
        self.shell.go(99)
        self.shell.go(-1)
        self.assertEqual(self.shell.current, 0)

    def test_next_goes_one_step_on_when_it_is_open(self):
        self.shell.next()
        self.assertEqual(self.shell.current, 1)
        self.shell.next()                                       # Look is still locked
        self.assertEqual(self.shell.current, 1)
        self.shell.setFact("ready", True)
        self.shell.next()
        self.assertEqual(self.shell.current, 2)

    def test_an_unknown_fact_is_ignored(self):
        self.shell.setFact("nonsense", True)
        self.assertEqual(self.states()["look"], "locked")

    def test_reduce_effects_is_saved_and_read_back(self):
        self.assertFalse(self.shell.reduceEffects)
        self.shell.reduceEffects = True
        self.assertTrue(self.Shell(self.path).reduceEffects)

    def test_switches_are_saved_and_unknown_ones_refused(self):
        self.shell.setSwitch("skip_auto_art", True)
        self.assertTrue(self.Shell(self.path).switchValue("skip_auto_art"))
        self.shell.setSwitch("account", True)
        self.assertFalse(self.shell.switchValue("account"))
        with open(self.path) as f:
            self.assertEqual(list(json.load(f)), list(st.SETTING_KEYS))

    def test_signals_fire_once_per_change(self):
        seen = {"steps": 0, "current": 0, "reduce": 0}
        self.shell.stepsChanged.connect(lambda: seen.__setitem__("steps", seen["steps"] + 1))
        self.shell.currentChanged.connect(lambda: seen.__setitem__("current", seen["current"] + 1))
        self.shell.reduceEffectsChanged.connect(lambda: seen.__setitem__("reduce", seen["reduce"] + 1))
        self.shell.setFact("ready", True)
        self.shell.setFact("ready", True)                       # no change: no signal
        self.shell.go(1)
        self.shell.go(1)
        self.shell.reduceEffects = True
        self.shell.reduceEffects = True
        self.assertEqual(seen, {"steps": 1, "current": 1, "reduce": 1})

    def test_a_corrupt_settings_file_gives_defaults(self):
        with open(self.path, "w") as f:
            f.write("{{{")
        shell = self.Shell(self.path)
        self.assertFalse(shell.reduceEffects)
        self.assertTrue(shell.switchValue("restart_steam"))


if __name__ == "__main__":
    unittest.main()
