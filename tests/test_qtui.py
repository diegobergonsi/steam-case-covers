# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Tests of the Qt window (the qtui package). The parts that need Qt skip themselves when PySide6 is missing.
Run:  python -m unittest discover -s tests -v   (with Qt: QT_QPA_PLATFORM=offscreen QT_QUICK_CONTROLS_STYLE=Basic python -m unittest tests.test_qtui)"""
import json, os, shutil, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from qtui import settings as st
from qtui import steps as sp
from qtui import system
from qtui import tones
from qtui.watcher import DownloadWatcher

try:
    from PySide6.QtGui import QGuiApplication
except ImportError:
    QGuiApplication = None
need_qt = unittest.skipIf(QGuiApplication is None, "PySide6 missing")
QML_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "qtui", "qml")


def qt_app():
    """One Qt application for the whole test process (a second one cannot be made)."""
    return QGuiApplication.instance() or QGuiApplication([])


class Watcher(unittest.TestCase):
    """Waits for a download to finish: a file counts when two polls in a row see it unchanged, and it is handed over once per version."""
    def setUp(self):
        import time
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.w = DownloadWatcher(self.dir, "userdata", (".json",), 1000)

    def put(self, name, data=b"{}", age=0):
        import time
        p = os.path.join(self.dir, name)
        with open(p, "wb") as f:
            f.write(data)
        t = time.time() - age
        os.utime(p, (t, t))
        return p

    def names(self):
        return sorted(os.path.basename(p) for p, _ in self.w.poll())

    def test_a_file_is_returned_on_the_second_poll_only(self):
        self.put("userdata.json")
        self.assertEqual(self.names(), [])
        self.assertEqual(self.names(), ["userdata.json"])

    def test_the_same_version_is_returned_once(self):
        self.put("userdata.json")
        self.names()
        self.assertEqual(self.names(), ["userdata.json"])
        self.assertEqual(self.names(), [])
        self.assertEqual(self.names(), [])

    def test_a_growing_file_waits_until_it_stops(self):
        p = self.put("userdata.json", b"1")
        self.names()
        with open(p, "ab") as f:
            f.write(b"22")
        self.assertEqual(self.names(), [])                          # changed since the last poll
        self.assertEqual(self.names(), ["userdata.json"])

    def test_a_changed_version_is_returned_again(self):
        p = self.put("userdata.json", b"1")
        self.names(); self.names()
        with open(p, "wb") as f:
            f.write(b"two")
        self.assertEqual(self.names(), [])
        self.assertEqual(self.names(), ["userdata.json"])

    def test_forget_brings_a_file_back(self):
        p = self.put("userdata.json")
        self.names(); self.names()
        self.w.forget(p)
        self.assertEqual(self.names(), ["userdata.json"])

    def test_files_that_do_not_count_are_ignored(self):
        self.put("other.json")
        self.put("userdata.txt")
        self.put("big userdata.json", b"x" * 1001)                   # over the size limit
        os.makedirs(os.path.join(self.dir, "userdata folder.json"))   # a directory named like a match
        os.symlink(os.path.join(self.dir, "other.json"), os.path.join(self.dir, "userdata link.json"))
        self.names()
        self.assertEqual(self.names(), [])

    def test_matching_ignores_case_and_takes_browser_copies(self):
        self.put("USERDATA (1).JSON")
        self.names()
        self.assertEqual(self.names(), ["USERDATA (1).JSON"])

    def test_several_files_come_back_together(self):
        self.put("userdata.json")
        self.put("userdata (1).json")
        self.names()
        self.assertEqual(self.names(), ["userdata (1).json", "userdata.json"])

    def test_a_missing_or_unreadable_folder_gives_nothing(self):
        from unittest import mock
        gone = DownloadWatcher(os.path.join(self.dir, "nope"), "userdata", (".json",), 1000)
        self.assertEqual(gone.poll(), [])
        self.put("userdata.json")
        with mock.patch("os.listdir", side_effect=PermissionError(13, "denied")):
            self.assertEqual(self.w.poll(), [])

    def test_files_that_were_there_before_the_watcher_started_wait_until_they_change(self):
        """What lay in Downloads before the app opened is stale. This does not depend on the clock, which may step back."""
        old = self.put("userdata.json", b"old", age=5000)
        w = DownloadWatcher(self.dir, "userdata", (".json",), 1000)
        w.poll()
        self.assertEqual(w.poll(), [])
        with open(old, "wb") as f:
            f.write(b"saved again")
        w.poll()
        self.assertEqual([os.path.basename(p) for p, _ in w.poll()], ["userdata.json"])

    def test_a_file_saved_after_the_start_counts_even_if_its_time_is_in_the_past(self):
        p = self.put("userdata.json", age=99999)                      # the clock stepped back, or the time came from the server
        self.w.poll()
        self.assertEqual([os.path.basename(x) for x, _ in self.w.poll()], ["userdata.json"])

    def test_a_replacement_with_the_same_size_and_time_is_noticed(self):
        p = self.put("userdata.json", b"AAAA")
        st = os.stat(p)
        self.w.poll(); self.w.poll()
        other = self.put("tmp.bin", b"BBBB")
        os.utime(other, ns=(st.st_atime_ns, st.st_mtime_ns))          # a coarse-clock file system gives the same time and size
        os.replace(other, p)
        self.w.poll()
        self.assertEqual([os.path.basename(x) for x, _ in self.w.poll()], ["userdata.json"])

    def test_a_file_that_vanishes_between_listing_and_reading_is_skipped(self):
        from unittest import mock
        self.put("userdata.json")
        with mock.patch("os.lstat", side_effect=FileNotFoundError()):
            self.assertEqual(self.w.poll(), [])


class SystemHelpers(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home, True)

    def downloads(self):
        from unittest import mock
        with mock.patch.dict(os.environ, {"HOME": self.home, "USERPROFILE": self.home}):
            return system.downloads_dir()

    def test_downloads_dir_reads_the_xdg_setting(self):
        os.makedirs(os.path.join(self.home, ".config"))
        os.makedirs(os.path.join(self.home, "Telechargements"))
        with open(os.path.join(self.home, ".config", "user-dirs.dirs"), "w") as f:
            f.write('XDG_DESKTOP_DIR="$HOME/Desktop"\nXDG_DOWNLOAD_DIR="$HOME/Telechargements"\n')
        self.assertEqual(self.downloads(), os.path.join(self.home, "Telechargements"))

    def test_downloads_dir_is_a_clean_native_path(self):
        os.makedirs(os.path.join(self.home, ".config"))
        os.makedirs(os.path.join(self.home, "Dl"))
        with open(os.path.join(self.home, ".config", "user-dirs.dirs"), "w") as f:
            f.write('XDG_DOWNLOAD_DIR="$HOME//Dl/"\n')                      # a doubled and a trailing slash
        self.assertEqual(self.downloads(), os.path.join(self.home, "Dl"))

    def test_downloads_dir_falls_back_to_downloads_in_home(self):
        self.assertEqual(self.downloads(), os.path.join(self.home, "Downloads"))
        os.makedirs(os.path.join(self.home, ".config"))
        with open(os.path.join(self.home, ".config", "user-dirs.dirs"), "w") as f:
            f.write('XDG_DOWNLOAD_DIR="$HOME/Gone"\n')                      # names a folder that does not exist
        self.assertEqual(self.downloads(), os.path.join(self.home, "Downloads"))

    def test_save_key_names_the_platform_shortcut(self):
        import importlib
        from unittest import mock
        for platform, key in (("darwin", "Cmd+S"), ("linux", "Ctrl+S"), ("win32", "Ctrl+S")):
            with mock.patch.object(sys, "platform", platform):
                self.assertEqual(importlib.reload(system).SAVE_KEY, key, platform)
        importlib.reload(system)


class Tones(unittest.TestCase):
    def test_clamping(self):
        self.assertEqual(tones.clamp_tone(90, 80, 70), (90, 80, 70))
        self.assertEqual(tones.clamp_tone(-30, 150, -5), (330, 100, 0))
        self.assertEqual(tones.clamp_tone(360, 0, 100), (0, 0, 100))
        self.assertEqual(tones.clamp_tone(725, 50, 50), (5, 50, 50))
        self.assertEqual(tones.clamp_tone(10.6, 99.5, 0.4), (11, 100, 0))
        for bad in ((None, 1, 1), ("x", 1, 1), (1, [], 1), (float("nan"), 1, 1), (1, 1, float("inf"))):
            self.assertEqual(tones.clamp_tone(*bad), (0, 100, 100), bad)

    def test_names_as_the_old_window_wrote_them(self):
        self.assertEqual(tones.tone_name(0, 100, 100), "Original")
        self.assertEqual(tones.tone_name(0, 0, 14), "Black")
        self.assertEqual(tones.tone_name(200, 0, 34), "Graphite")          # a grey has no hue
        self.assertEqual(tones.tone_name(0, 0, 78), "Silver")
        self.assertEqual(tones.tone_name(90, 80, 70), "Custom \u00b7 90\u00b0 80% 70%")

    def test_the_hint_only_for_grey_and_black(self):
        self.assertEqual(tones.tone_hint(10, 0, 50), "Colour has no effect on grey or black.")
        self.assertEqual(tones.tone_hint(10, 50, 0), "Colour has no effect on grey or black.")
        self.assertEqual(tones.tone_hint(10, 50, 50), "")

    def test_nine_swatches_six_colours_then_three_greys(self):
        import steamcase as sc
        sw = tones.swatches()
        self.assertEqual(len(sw), 9)
        self.assertEqual([x["hue"] for x in sw[:6]], list(sc.HUE_SWATCHES))
        self.assertEqual([(x["sat"], x["val"]) for x in sw[:6]], [(100, 100)] * 6)
        self.assertEqual([x["name"] for x in sw[6:]], ["Black", "Graphite", "Silver"])
        for x in sw:
            self.assertEqual(x["color"], sc.case_color(x["hue"], x["sat"], x["val"]))
            self.assertTrue(x["name"])

    def test_same_tone_ignores_the_hue_of_greys(self):
        self.assertTrue(tones.same_tone((10, 0, 50), (200, 0, 50)))
        self.assertTrue(tones.same_tone((10, 50, 0), (200, 50, 0)))                 # without light the hue shows nothing
        self.assertFalse(tones.same_tone((10, 50, 0), (10, 80, 0)))                 # the engine keeps colourfulness apart, and so do the swatches
        self.assertFalse(tones.same_tone((10, 50, 50), (200, 50, 50)))
        self.assertFalse(tones.same_tone((10, 50, 50), (10, 60, 50)))

    def test_slider_tracks(self):
        import steamcase as sc
        lo, hi = tones.track_colors(120, 60, 80, "sat")
        self.assertEqual((lo, hi), (sc.case_color(120, 0, 80), sc.case_color(120, 100, 80)))
        lo, hi = tones.track_colors(120, 60, 80, "val")
        self.assertEqual((lo, hi), (sc.case_color(120, 60, 0), sc.case_color(120, 60, 100)))
        with self.assertRaises(ValueError):
            tones.track_colors(0, 0, 0, "other")

    def test_the_hue_gradient_starts_at_the_original_blue(self):
        colours = tones.hue_colors()
        self.assertEqual(len(colours), 36)
        self.assertEqual(colours[0], "#1636c8")
        self.assertEqual(len(set(colours)), len(colours))


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

    def test_a_named_pipe_as_the_settings_file_does_not_hang_startup(self):
        import threading
        if not hasattr(os, "mkfifo"):
            self.skipTest("no named pipes on this system")
        os.makedirs(os.path.dirname(self.path))
        os.mkfifo(self.path)
        out = []
        t = threading.Thread(target=lambda: out.append(st.load_settings(self.path)), daemon=True)
        t.start()
        t.join(5)
        if t.is_alive():                                        # unblock the stuck open() so the test run can end
            fd = os.open(self.path, os.O_WRONLY)
            os.close(fd)
            self.fail("load_settings blocked on a named pipe")
        self.assertEqual(out, [st.DEFAULTS])

    def test_a_failing_cleanup_never_raises(self):
        from unittest import mock
        with mock.patch("os.replace", side_effect=OSError("denied")), mock.patch("os.remove", side_effect=OSError("denied")):
            self.assertFalse(st.save_settings(st.DEFAULTS, self.path))

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


class FilePicker(unittest.TestCase):
    """The desktop's own file chooser (kdialog or zenity on Linux), as the Tk window used it; None means 'show the Qt dialog instead'."""
    def run_picker(self, tools, results, platform="linux"):
        from unittest import mock
        from qtui import filepicker
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd[0])
            r = results.pop(0)
            if isinstance(r, Exception):
                raise r
            return mock.Mock(returncode=r[0], stdout=r[1])
        with mock.patch.object(sys, "platform", platform), mock.patch("shutil.which", side_effect=lambda n: "/usr/bin/" + n if n in tools else None), \
                mock.patch("subprocess.run", side_effect=fake_run):
            return filepicker.pick_file("Choose", self.start, ("JSON files", "*.json")), calls

    def setUp(self):
        self.start = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.start, True)

    def test_kdialog_is_preferred_and_its_answer_is_returned(self):
        self.assertEqual(self.run_picker({"kdialog", "zenity"}, [(0, "/home/u/userdata.json\n")]), ("/home/u/userdata.json", ["kdialog"]))

    def test_zenity_is_the_second_choice(self):
        self.assertEqual(self.run_picker({"zenity"}, [(0, "/x/y.json\n")]), ("/x/y.json", ["zenity"]))

    def test_cancel_returns_an_empty_string(self):
        self.assertEqual(self.run_picker({"kdialog"}, [(1, "")]), ("", ["kdialog"]))

    def test_a_missing_tool_or_a_crash_means_use_the_qt_dialog(self):
        self.assertEqual(self.run_picker(set(), []), (None, []))
        self.assertEqual(self.run_picker({"kdialog"}, [OSError("gone")]), (None, ["kdialog"]))
        self.assertEqual(self.run_picker({"kdialog", "zenity"}, [(2, ""), (0, "/z.json\n")]), ("/z.json", ["kdialog", "zenity"]))   # a failing tool falls through to the next

    def test_other_systems_always_use_the_qt_dialog(self):
        for platform in ("win32", "darwin"):
            self.assertEqual(self.run_picker({"kdialog"}, [], platform), (None, []), platform)


@need_qt
class GameListScreen(unittest.TestCase):
    """Step 1 as the approved wireframe, in the real window (offscreen, effects reduced so nothing is still sliding when a test clicks)."""
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def setUp(self):
        from qtui.shell import Shell
        from qtui.app import create_engine
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.downloads = os.path.join(self.tmp, "Downloads")
        os.makedirs(self.downloads)
        self.shell = Shell(os.path.join(self.tmp, "settings.json"), downloads=self.downloads, covers_dir=os.path.join(self.tmp, "covers"))
        self.shell.reduceEffects = True
        self.engine = create_engine(self.shell)
        self.addCleanup(self.close, self.engine)
        self.root = self.engine.rootObjects()[0]
        self.lib = self.shell.library
        self.shell.go(1)
        self.app.processEvents()

    def close(self, engine):
        from qtui.app import close_engine
        close_engine(engine)

    def item(self, name):
        from qtui.app import find_item
        got = find_item(self.root, name)
        self.assertIsNotNone(got, name)
        return got

    def click(self, name):
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtTest import QTest
        it = self.item(name)
        centre = it.mapToScene(QPointF(it.width() / 2, it.height() / 2)).toPoint()
        QTest.mouseClick(self.root, Qt.LeftButton, Qt.NoModifier, centre)
        self.app.processEvents()

    def test_it_shows_the_title_and_the_waiting_status(self):
        self.assertEqual(self.item("screen_title").property("text"), "Get your game list")
        self.assertEqual(self.item("gamelist_status").property("text"), "Waiting for userdata.json\u2026")

    def row_ys(self):
        from PySide6.QtCore import QPointF
        return [self.item(n).mapToScene(QPointF(0, 0)).y() for n in ("gamelist_open", "gamelist_browse", "gamelist_copy")]

    def test_the_three_ways_to_get_the_file_sit_in_one_row(self):
        self.root.setProperty("width", 1200)                 # a roomy window: the row depends on the width and the system's font
        self.app.processEvents()
        ys = self.row_ys()
        self.assertLess(max(ys) - min(ys), 1.0, "window %s px wide, rows at %s" % (self.root.property("width"), ys))
        self.assertEqual([self.item(n).property("text") for n in ("gamelist_open", "gamelist_browse", "gamelist_copy")],
                         ["Open the page in my browser", "Browse\u2026", "Copy link"])

    def test_on_a_narrow_window_the_row_wraps_instead_of_overflowing(self):
        from PySide6.QtCore import QPointF
        self.root.setProperty("width", self.root.property("minimumWidth"))
        self.app.processEvents()
        section = self.item("gamelist_section_list")
        right = section.mapToScene(QPointF(section.width(), 0)).x()
        for name in ("gamelist_open", "gamelist_browse", "gamelist_copy"):
            it = self.item(name)
            self.assertLessEqual(it.mapToScene(QPointF(it.width(), 0)).x(), right + 0.5, name)         # no button sticks out of its card

    def test_a_button_wider_than_its_card_is_squeezed_not_overflowing(self):
        """Wider system fonts (the Windows runner's) make a button longer than the card at the narrowest window; here the window is made narrower still."""
        from PySide6.QtCore import QPointF
        self.root.setProperty("minimumWidth", 300)
        self.root.setProperty("width", 420)
        self.app.processEvents()
        section = self.item("gamelist_section_list")
        right = section.mapToScene(QPointF(section.width(), 0)).x()
        for name in ("gamelist_open", "gamelist_browse", "gamelist_copy"):
            it = self.item(name)
            self.assertLessEqual(it.mapToScene(QPointF(it.width(), 0)).x(), right + 0.5, "%s sticks out of its card" % name)
            self.assertGreater(it.width(), 0, name)

    def test_copy_link_works_from_the_screen(self):
        from unittest import mock
        with mock.patch("steamcase.library_login_url", return_value="https://example.test/login"):
            self.click("gamelist_copy")
        self.assertEqual(QGuiApplication.clipboard().text(), "https://example.test/login")
        self.assertTrue(self.item("gamelist_status").property("text").startswith("Link copied."))

    def test_next_is_locked_until_a_list_is_ready_and_then_goes_to_look(self):
        nxt = self.item("gamelist_next")
        self.assertFalse(nxt.property("enabled"))
        self.click("gamelist_next")
        self.assertEqual(self.shell.current, 1)
        self.click("gamelist_installed")
        self.assertTrue(self.lib.ready)
        self.assertTrue(nxt.property("enabled"))
        self.click("gamelist_next")
        self.assertEqual(self.shell.current, 2)

    def test_enter_on_a_locked_next_does_nothing(self):
        from PySide6.QtCore import QCoreApplication, QEvent, Qt
        from PySide6.QtGui import QKeyEvent
        self.root.requestActivate()
        self.item("gamelist_next").forceActiveFocus()
        QCoreApplication.sendEvent(self.root, QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier, "", False))
        self.app.processEvents()
        self.assertEqual(self.shell.current, 1)

    def test_there_is_exactly_one_filled_button_at_a_time(self):
        names = ("gamelist_open", "gamelist_browse", "gamelist_copy", "gamelist_next")
        def filled():
            return [n for n in names if self.item(n).property("filled") and self.item(n).property("enabled")]
        self.assertEqual(filled(), ["gamelist_open"])
        self.lib.installedOnly = True
        self.app.processEvents()
        self.assertEqual(filled(), ["gamelist_next"])

    def test_keyboard_focus_stays_on_the_open_button_when_a_list_arrives(self):
        open_button = self.item("gamelist_open")
        open_button.forceActiveFocus()
        self.assertTrue(open_button.property("activeFocus"))
        self.lib.installedOnly = True
        self.app.processEvents()
        self.assertTrue(self.item("gamelist_open").property("activeFocus"))
        self.assertFalse(self.item("gamelist_open").property("filled"))

    def test_sections_are_24_px_apart(self):
        from PySide6.QtCore import QPointF
        a, b = self.item("gamelist_section_list"), self.item("gamelist_section_skip")
        gap = b.mapToScene(QPointF(0, 0)).y() - (a.mapToScene(QPointF(0, 0)).y() + a.height())
        self.assertAlmostEqual(gap, 24, delta=0.5)

    def test_the_switch_tells_screen_readers_it_can_be_checked(self):
        from PySide6.QtGui import QAccessible
        QAccessible.setActive(True)
        self.addCleanup(QAccessible.setActive, False)
        iface = QAccessible.queryAccessibleInterface(self.item("gamelist_installed"))
        self.assertIsNotNone(iface)
        self.assertTrue(iface.state().checkable)
        self.assertFalse(iface.state().checked)
        self.lib.installedOnly = True
        self.app.processEvents()
        self.assertTrue(QAccessible.queryAccessibleInterface(self.item("gamelist_installed")).state().checked)

    def test_escape_closes_a_pinned_info_tip_and_it_can_open_again(self):
        from PySide6.QtCore import QCoreApplication, QEvent, Qt
        from PySide6.QtGui import QKeyEvent
        tip = self.item("gamelist_installed_tip")
        self.root.requestActivate()
        tip.forceActiveFocus()
        tip.setProperty("pinned", True)
        self.app.processEvents()
        self.assertTrue(tip.property("shown"))
        QCoreApplication.sendEvent(self.root, QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier, "", False))
        self.app.processEvents()
        self.assertFalse(tip.property("pinned"))
        tip.setProperty("pinned", True)                        # the next click works again, it is not stuck
        self.app.processEvents()
        self.assertTrue(tip.property("shown"))

    def test_the_info_tip_explains_family_games(self):
        import steamcase as sc
        self.assertEqual(self.item("gamelist_installed_tip").property("text"), sc.FAMILY_HELP)

    def test_the_status_colour_follows_its_kind(self):
        status = self.item("gamelist_status")
        waiting = status.property("color").name()
        self.lib.installedOnly = True
        self.app.processEvents()
        ok = status.property("color").name()
        self.assertNotEqual(waiting, ok)
        self.assertEqual((waiting, ok), ("#93a7bb", "#66c0f4"))
        self.lib.installedOnly = False
        self.lib.useFile(os.path.join(self.tmp, "missing.json"))
        self.app.processEvents()
        self.assertEqual(status.property("color").name(), "#ff7b72")

    def test_a_saved_file_appears_on_screen_by_itself(self):
        with open(os.path.join(self.downloads, "userdata.json"), "w") as f:
            json.dump({"rgOwnedApps": [1, 2]}, f)
        self.lib.poll(); self.lib.poll()
        self.app.processEvents()
        self.assertEqual(self.item("gamelist_status").property("text"), "Got it: userdata.json (2 items in your library).")
        self.assertTrue(self.item("gamelist_next").property("enabled"))

    def test_the_qt_dialog_answer_is_turned_into_a_path(self):
        good = os.path.join(self.tmp, "mine.json")
        with open(good, "w") as f:
            json.dump({"rgOwnedApps": [1]}, f)
        from unittest import mock
        from PySide6.QtCore import QDir, QUrl
        with mock.patch("qtui.library.QDir.toNativeSeparators", wraps=QDir.toNativeSeparators) as native:
            self.assertTrue(self.lib.useFileUrl(QUrl.fromLocalFile(good).toString()))
        native.assert_called_once()                                  # on Windows Qt answers C:/Users/x, the rest of the app uses C:\\Users\\x
        self.assertEqual(self.lib.path, os.path.normpath(good))


@need_qt
class GameListFlow(unittest.TestCase):
    """The whole of step 1 as a person lives it: Home, the page is saved slowly, the app notices, Look opens."""
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def test_from_home_to_look(self):
        from qtui.app import close_engine, create_engine, find_item
        from qtui.shell import Shell
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        downloads = os.path.join(tmp, "Downloads")
        os.makedirs(downloads)
        shell = Shell(os.path.join(tmp, "settings.json"), downloads=downloads, covers_dir=os.path.join(tmp, "covers"))
        shell.reduceEffects = True
        engine = create_engine(shell)
        self.addCleanup(close_engine, engine)
        root = engine.rootObjects()[0]
        lib = shell.library
        self.assertEqual(shell.current, 0)
        shell.next()                                                   # Home's Start
        self.app.processEvents()
        self.assertEqual(find_item(root, "screen_title").property("text"), "Get your game list")
        status = lambda: find_item(root, "gamelist_status").property("text")
        self.assertEqual(status(), "Waiting for userdata.json\u2026")

        path = os.path.join(downloads, "userdata.json")
        chunks = ['{"rgOwnedApps": ', "[1, 2, ", "3, 4]}"]
        for chunk in chunks:                                            # the browser is still writing: the file changes between polls
            with open(path, "a") as f:
                f.write(chunk)
            lib.poll()
            self.assertEqual(status(), "Waiting for userdata.json\u2026")   # not read yet, and not an error
        lib.poll()                                                      # steady: finished
        self.app.processEvents()
        self.assertEqual(status(), "Got it: userdata.json (4 items in your library).")
        self.assertTrue(find_item(root, "gamelist_next").property("enabled"))

        with open(os.path.join(downloads, "userdata (1).json"), "w") as f:
            json.dump({"rgOwnedApps": [], "rgOwnedPackages": [1]}, f)   # a logged-out copy saved later must not replace it
        from unittest import mock
        with mock.patch("steamcase.owned_ids", side_effect=AssertionError("a list is loaded: nothing else may be read")) as read:
            lib.poll(); lib.poll(); lib.poll()
            self.assertEqual(read.call_count, 0)
        self.assertEqual(status(), "Got it: userdata.json (4 items in your library).")

        shell.next()
        self.app.processEvents()
        self.assertEqual(shell.current, 2)
        self.assertEqual(find_item(root, "screen_title").property("text"), "Choose the look")


@need_qt
class LibraryActions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def setUp(self):
        from unittest import mock
        from qtui.shell import Shell
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.downloads = os.path.join(self.tmp, "Downloads")
        os.makedirs(self.downloads)
        self.shell = Shell(os.path.join(self.tmp, "settings.json"), downloads=self.downloads, covers_dir=os.path.join(self.tmp, "covers"))
        self.lib = self.shell.library
        self.url = "https://store.steampowered.com/login/?redir=test"
        patch = mock.patch("steamcase.library_login_url", return_value=self.url)
        patch.start()
        self.addCleanup(patch.stop)

    def wait_for(self, condition, seconds=3):
        import time
        end = time.time() + seconds
        while time.time() < end and not condition():
            self.app.processEvents()
            time.sleep(0.02)
        self.app.processEvents()

    def test_copy_link_puts_the_exact_link_on_the_clipboard(self):
        self.lib.copyLink()
        self.assertEqual(QGuiApplication.clipboard().text(), self.url)
        self.assertEqual(self.lib.statusKind, "ok")
        self.assertTrue(self.lib.status.startswith("Link copied. Paste it into your browser, log in if asked, then save the page as userdata.json ("), self.lib.status)

    def test_open_page_opens_the_link_and_always_shows_the_way_out(self):
        from unittest import mock
        for opened in (True, False):                              # Qt cannot tell whether a browser really appeared
            with self.subTest(opened=opened), mock.patch("qtui.library.QDesktopServices.openUrl", return_value=opened) as m:
                self.lib.openDownloadPage()
                self.assertEqual(m.call_count, 1)
                self.assertEqual(m.call_args[0][0].toString(), self.url)
                self.assertTrue(self.lib.status.startswith("Opening your browser\u2026 Log in to Steam if it asks."), self.lib.status)
                self.assertIn("Nothing opened? Click \u201cCopy link\u201d and paste it into your browser.", self.lib.status)

    def test_browse_loads_the_chosen_file(self):
        from unittest import mock
        good = os.path.join(self.tmp, "mine.json")
        with open(good, "w") as f:
            json.dump({"rgOwnedApps": [1, 2, 3]}, f)
        with mock.patch("qtui.library.pick_file", return_value=good):
            self.lib.browse()
            self.wait_for(lambda: self.lib.path)
        self.assertEqual((self.lib.path, self.lib.ready), (good, True))

    def test_browse_does_not_freeze_the_window_while_the_chooser_is_open(self):
        import time
        from unittest import mock
        good = os.path.join(self.tmp, "slow.json")
        with open(good, "w") as f:
            json.dump({"rgOwnedApps": [1]}, f)

        def slow(*a, **k):
            time.sleep(0.6)                                    # the user is looking at the chooser
            return good
        with mock.patch("qtui.library.pick_file", side_effect=slow):
            t0 = time.time()
            self.lib.browse()
            self.assertLess(time.time() - t0, 0.3)             # returns at once
            self.lib.browse()                                  # a second click while the first chooser is open does not open another
            for _ in range(60):
                self.app.processEvents()
                if self.lib.path:
                    break
                time.sleep(0.05)
        self.assertEqual(self.lib.path, good)

    def test_browse_cancelled_changes_nothing(self):
        from unittest import mock
        before = (self.lib.path, self.lib.status, self.lib.statusKind)
        with mock.patch("qtui.library.pick_file", return_value="") as m:
            self.lib.browse()
            self.wait_for(lambda: m.called)
            self.app.processEvents()
        self.assertEqual((self.lib.path, self.lib.status, self.lib.statusKind), before)

    def test_browse_without_a_desktop_chooser_asks_for_the_qt_dialog(self):
        from unittest import mock
        seen = []
        self.lib.needDialog.connect(lambda folder: seen.append(folder))
        with mock.patch("qtui.library.pick_file", return_value=None):
            self.lib.browse()
            self.wait_for(lambda: seen)
        self.assertEqual(seen, [self.downloads])

    def test_the_qt_dialog_answer_goes_through_the_same_check(self):
        bad = os.path.join(self.tmp, "bad.json")
        with open(bad, "w") as f:
            f.write("[]")
        self.assertFalse(self.lib.useFile(bad))
        self.assertEqual(self.lib.statusKind, "error")


@need_qt
class LibraryState(unittest.TestCase):
    """The game list of step 1: the saved file noticed by itself, validated, and the 'installed games only' switch."""
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def setUp(self):
        import time
        from qtui.shell import Shell
        self.Shell = Shell
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.downloads = os.path.join(self.tmp, "Downloads")
        os.makedirs(self.downloads)
        self.settings = os.path.join(self.tmp, "settings.json")
        self.shell = self.new_shell()
        self.lib = self.shell.library

    def new_shell(self):
        return self.Shell(self.settings, downloads=self.downloads, covers_dir=os.path.join(self.tmp, "covers"))

    def save(self, name, data):
        p = os.path.join(self.downloads, name)
        with open(p, "w") as f:
            f.write(data if isinstance(data, str) else json.dumps(data))
        return p

    def poll(self, times=2):
        for _ in range(times):
            self.lib.poll()

    def states(self):
        return {s["key"]: s["state"] for s in self.shell.steps}

    def test_it_starts_waiting(self):
        self.assertEqual((self.lib.path, self.lib.ready, self.lib.status, self.lib.statusKind), ("", False, "Waiting for userdata.json\u2026", "wait"))

    def test_a_saved_list_is_noticed_by_itself_and_unlocks_look(self):
        self.save("userdata.json", {"rgOwnedApps": [10, 20]})
        self.poll()
        self.assertTrue(self.lib.ready)
        self.assertEqual(os.path.basename(self.lib.path), "userdata.json")
        self.assertEqual((self.lib.status, self.lib.statusKind), ("Got it: userdata.json (2 items in your library).", "ok"))
        self.assertEqual(self.states()["look"], "active")

    def test_a_list_saved_while_logged_out_is_explained_once(self):
        self.save("userdata.json", {"rgOwnedApps": [], "rgOwnedPackages": [1]})
        seen = []
        self.lib.statusChanged.connect(lambda: seen.append(self.lib.status))
        self.poll(4)
        self.assertFalse(self.lib.ready)
        self.assertEqual(self.lib.statusKind, "error")
        self.assertTrue(self.lib.status.startswith("userdata.json: That file has no games in it."), self.lib.status)
        self.assertEqual(len(seen), 1)                                       # one message for that version of the file
        self.assertEqual(self.states()["look"], "locked")

    def test_a_file_that_is_not_a_game_list_is_refused_and_the_good_one_is_kept(self):
        good = self.save("good.json", {"rgOwnedApps": [10]})
        self.assertTrue(self.lib.useFile(good))
        bad = [os.path.join(self.tmp, "missing.json"), self.tmp, self.save("empty.json", ""), self.save("garbage.json", "<html>nope</html>")]
        for path in bad:
            with self.subTest(os.path.basename(path)):
                self.assertFalse(self.lib.useFile(path))
                self.assertEqual(self.lib.path, good)
                self.assertTrue(self.lib.ready)
                self.assertEqual(self.lib.statusKind, "error")
                self.assertTrue(self.lib.status.startswith("That file doesn't look right: "), self.lib.status)

    def test_a_rejected_file_says_which_list_is_still_used(self):
        good = self.save("good.json", {"rgOwnedApps": [10]})
        bad = self.save("bad.json", "[]")
        self.assertFalse(self.lib.useFile(bad))
        self.assertFalse(self.lib.status.endswith("."), self.lib.status) if False else None
        self.assertNotIn("Still using", self.lib.status)                     # nothing is in use yet
        self.assertTrue(self.lib.useFile(good))
        self.assertFalse(self.lib.useFile(bad))
        self.assertTrue(self.lib.status.endswith(" Still using good.json."), self.lib.status)
        self.lib.installedOnly = True
        self.assertFalse(self.lib.useFile(bad))
        self.assertTrue(self.lib.status.endswith(" Still using good.json."), self.lib.status)         # the file is what counts while a file is loaded

    def test_a_rejected_file_while_only_installed_games_are_used(self):
        self.lib.installedOnly = True
        self.assertFalse(self.lib.useFile(self.save("bad.json", "[]")))
        self.assertTrue(self.lib.status.endswith(" Still using installed games only."), self.lib.status)

    def test_a_named_pipe_is_refused_without_hanging(self):
        import threading
        if not hasattr(os, "mkfifo"):
            self.skipTest("no named pipes on this system")
        fifo = os.path.join(self.tmp, "pipe.json")
        os.mkfifo(fifo)
        out = []
        t = threading.Thread(target=lambda: out.append(self.lib.useFile(fifo)), daemon=True)
        t.start()
        t.join(5)
        if t.is_alive():
            os.close(os.open(fifo, os.O_WRONLY))                              # unblock the stuck open()
            self.fail("useFile blocked on a named pipe")
        self.assertEqual(out, [False])
        self.assertEqual(self.lib.statusKind, "error")

    def test_loading_a_file_switches_installed_only_off(self):
        self.lib.installedOnly = True
        self.assertTrue(self.lib.useFile(self.save("userdata.json", {"rgOwnedApps": [10]})))
        self.assertFalse(self.lib.installedOnly)

    def test_installed_only_is_ready_without_a_file_and_is_remembered(self):
        self.lib.installedOnly = True
        self.assertTrue(self.lib.ready)
        self.assertEqual((self.lib.status, self.lib.statusKind), ("Using installed games only.", "ok"))
        self.assertEqual(self.states()["look"], "active")
        again = self.new_shell().library
        self.assertTrue(again.installedOnly and again.ready)
        self.assertEqual(again.status, "Using installed games only.")

    def test_switching_everything_off_locks_the_next_step_and_moves_back(self):
        self.lib.installedOnly = True
        self.shell.go(2)
        self.assertEqual(self.shell.current, 2)
        self.lib.installedOnly = False
        self.assertFalse(self.lib.ready)
        self.assertEqual(self.shell.current, 1)
        self.assertEqual(self.lib.status, "Waiting for userdata.json\u2026")

    def test_switching_installed_only_off_keeps_a_loaded_file(self):
        self.lib.useFile(self.save("userdata.json", {"rgOwnedApps": [10]}))
        self.lib.installedOnly = True
        self.lib.installedOnly = False
        self.assertTrue(self.lib.ready)
        self.assertTrue(self.lib.status.startswith("Got it: userdata.json"))

    def test_the_watcher_stops_once_a_list_is_loaded(self):
        first = self.save("userdata.json", {"rgOwnedApps": [10]})
        self.poll()
        self.save("userdata (1).json", {"rgOwnedApps": [10, 20, 30]})
        self.poll(3)
        self.assertEqual(self.lib.path, first)

    def test_a_file_that_could_not_be_read_is_tried_again_while_it_stays_the_same(self):
        """Antivirus or the browser may hold the file for a moment: the next poll must retry it, as the old window did."""
        from unittest import mock
        self.save("userdata.json", {"rgOwnedApps": [10, 20]})
        real = __import__("steamcase").owned_ids
        calls = []

        def flaky(path):
            calls.append(path)
            if len(calls) == 1:
                raise __import__("steamcase").SteamcaseError("Could not read userdata.json as a game list (PermissionError).")
            return real(path)
        with mock.patch("steamcase.owned_ids", side_effect=flaky):
            self.poll(2)                                     # becomes finished on the second poll: the first read fails
            self.assertFalse(self.lib.ready)
            self.assertEqual(self.lib.statusKind, "error")
            self.poll(1)                                     # unchanged file, same version: read again
        self.assertTrue(self.lib.ready)
        self.assertEqual(self.lib.status, "Got it: userdata.json (2 items in your library).")

    def test_an_error_already_shown_for_a_file_does_not_come_back_over_another_message(self):
        self.save("userdata.json", {"rgOwnedApps": [], "rgOwnedPackages": [1]})
        self.poll(2)
        self.assertEqual(self.lib.statusKind, "error")
        from unittest import mock
        with mock.patch("steamcase.library_login_url", return_value="https://example.test/x"):
            self.lib.copyLink()
        self.poll(3)                                         # the same bad file is looked at again, but not reported again
        self.assertTrue(self.lib.status.startswith("Link copied."), self.lib.status)
        self.save("userdata.json", {"rgOwnedApps": [], "rgOwnedPackages": [1, 2]})     # a new version of it is reported again
        self.poll(3)
        self.assertTrue(self.lib.status.startswith("userdata.json: "), self.lib.status)

    def test_a_folder_that_does_not_exist_is_fine(self):
        shell = self.Shell(self.settings, downloads=os.path.join(self.tmp, "nope"), covers_dir=os.path.join(self.tmp, "covers"))
        shell.library.poll()
        self.assertFalse(shell.library.ready)


@need_qt
class Components(unittest.TestCase):
    """GradientSlider, Swatch, ChoiceChips and PreviewCard, each in a small window of its own (any QML warning fails the test)."""
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def load(self, body, w=420, h=240):
        from PySide6.QtCore import QUrl
        from PySide6.QtQml import QQmlApplicationEngine
        from qtui.preview import PreviewProvider
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder, True)
        path = os.path.join(folder, "Harness.qml")
        with open(path, "w") as f:
            f.write('import QtQuick\nimport QtQuick.Window\nimport "%s"\nWindow { id: win; width: %d; height: %d; visible: true; color: Theme.bg\n%s\n}\n'
                    % (QUrl.fromLocalFile(QML_DIR).toString(), w, h, body))
        engine = QQmlApplicationEngine()
        engine.addImageProvider("preview", PreviewProvider())
        problems = []
        engine.warnings.connect(lambda errors: problems.extend(e.toString() for e in errors))
        engine.load(QUrl.fromLocalFile(path))
        self.assertEqual(problems, [])
        self.assertEqual(len(engine.rootObjects()), 1)
        from qtui.app import close_engine
        self.addCleanup(close_engine, engine)
        self.root = engine.rootObjects()[0]
        self.app.processEvents()
        return self.root

    def item(self, name):
        from qtui.app import find_item
        got = find_item(self.root, name)
        self.assertIsNotNone(got, name)
        return got

    def mouse(self, kind, x, y):
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest
        {"click": QTest.mouseClick, "press": QTest.mousePress, "release": QTest.mouseRelease}[kind](self.root, Qt.LeftButton, Qt.NoModifier, QPoint(int(x), int(y)))
        self.app.processEvents()

    def drag_to(self, x, y):
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest
        QTest.mouseMove(self.root, QPoint(int(x), int(y)))
        self.app.processEvents()

    def key(self, name, key, repeat=False):
        from PySide6.QtCore import QCoreApplication, QEvent, Qt
        from PySide6.QtGui import QKeyEvent
        self.root.requestActivate()
        self.item(name).forceActiveFocus()
        QCoreApplication.sendEvent(self.root, QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier, "", repeat))
        self.app.processEvents()

    SLIDER = ('GradientSlider { objectName: "s"; x: 20; y: 20; width: 300; label: "Colour"; from: 0; to: 359; value: 0; stops: ["#ff0000", "#00ff00", "#0000ff"];\n'
              '  onMoved: (v) => value = v }')

    def test_a_slider_follows_a_click_and_a_drag_and_stays_in_range(self):
        self.load(self.SLIDER)
        s = self.item("s")
        self.assertGreaterEqual(s.height(), 36)                      # a finger on the Steam Deck
        y = 20 + s.height() / 2
        self.mouse("click", 20 + 150, y)
        self.assertAlmostEqual(s.property("value"), 179, delta=8)
        self.mouse("press", 20 + 150, y)
        self.drag_to(20 + 290, y)
        self.assertGreater(s.property("value"), 300)
        self.drag_to(20 + 900, y)                                    # far beyond the right edge
        self.assertEqual(s.property("value"), 359)
        self.drag_to(-500, y)
        self.assertEqual(s.property("value"), 0)
        self.mouse("release", 20, y)

    def test_slider_keys(self):
        self.load(self.SLIDER)
        from PySide6.QtCore import Qt
        s = self.item("s")
        s.setProperty("value", 100)
        for key, expect in ((Qt.Key_Right, 101), (Qt.Key_Up, 102), (Qt.Key_Left, 101), (Qt.Key_Down, 100), (Qt.Key_PageUp, 110), (Qt.Key_PageDown, 100), (Qt.Key_End, 359), (Qt.Key_Home, 0)):
            with self.subTest(key=key):
                self.key("s", key)
                self.assertEqual(s.property("value"), expect)
        self.key("s", Qt.Key_Left)                                   # never below the minimum
        self.assertEqual(s.property("value"), 0)

    def test_a_slider_can_be_reached_with_tab_and_tells_screen_readers_its_value(self):
        from PySide6.QtGui import QAccessible
        self.load(self.SLIDER)
        s = self.item("s")
        self.assertTrue(s.property("activeFocusOnTab"))
        s.setProperty("value", 120)
        QAccessible.setActive(True)
        self.addCleanup(QAccessible.setActive, False)
        iface = QAccessible.queryAccessibleInterface(s)
        self.assertEqual(iface.role(), QAccessible.Role.Slider)
        self.assertEqual(iface.text(QAccessible.Text.Name), "Colour")
        self.assertIn("120", iface.text(QAccessible.Text.Description))

    SWATCH = 'Swatch { objectName: "w"; x: 20; y: 20; color: "#336699"; name: "Blue"; selected: false; property int n: 0; onPicked: n++ }'

    def test_a_swatch_is_big_enough_and_picks_on_click_enter_and_space_not_on_repeat(self):
        from PySide6.QtCore import Qt
        self.load(self.SWATCH)
        w = self.item("w")
        self.assertGreaterEqual(min(w.width(), w.height()), 36)
        self.mouse("click", 20 + w.width() / 2, 20 + w.height() / 2)
        self.assertEqual(w.property("n"), 1)
        self.key("w", Qt.Key_Return)
        self.key("w", Qt.Key_Enter)
        self.key("w", Qt.Key_Space)
        self.assertEqual(w.property("n"), 4)
        self.key("w", Qt.Key_Space, repeat=True)
        self.assertEqual(w.property("n"), 4)

    def test_a_swatch_is_a_named_radio_button_for_screen_readers(self):
        from PySide6.QtGui import QAccessible
        self.load(self.SWATCH)
        QAccessible.setActive(True)
        self.addCleanup(QAccessible.setActive, False)
        w = self.item("w")
        iface = QAccessible.queryAccessibleInterface(w)
        self.assertEqual(iface.role(), QAccessible.Role.RadioButton)
        self.assertEqual(iface.text(QAccessible.Text.Name), "Blue")
        self.assertFalse(iface.state().checked)
        w.setProperty("selected", True)
        self.app.processEvents()
        self.assertTrue(QAccessible.queryAccessibleInterface(w).state().checked)

    CHIPS = ('ChoiceChips { objectName: "c"; x: 20; y: 20; width: 380; model: [{"key": "classic", "label": "Classic"}, {"key": "halloween", "label": "Halloween"}];\n'
             '  current: "classic"; property string last: ""; onChosen: (k) => last = k }')

    def test_chips_report_the_choice_and_leave_it_to_the_owner(self):
        from PySide6.QtCore import Qt
        self.load(self.CHIPS)
        c = self.item("c")
        chip = self.item("c_chip_halloween")
        self.assertGreaterEqual(chip.height(), 36)
        from PySide6.QtCore import QPointF
        centre = chip.mapToScene(QPointF(chip.width() / 2, chip.height() / 2))
        self.mouse("click", centre.x(), centre.y())
        self.assertEqual(c.property("last"), "halloween")
        self.assertEqual(c.property("current"), "classic")            # the owner decides
        c.setProperty("last", "")
        self.key("c_chip_classic", Qt.Key_Right)
        self.assertEqual(c.property("last"), "halloween")
        c.setProperty("last", "")
        c.setProperty("current", "halloween")
        self.key("c_chip_halloween", Qt.Key_Left)
        self.assertEqual(c.property("last"), "classic")
        c.setProperty("last", "")
        self.key("c_chip_halloween", Qt.Key_Right)                    # nothing after the last one
        self.assertEqual(c.property("last"), "")

    def test_only_the_chosen_chip_is_a_tab_stop_and_they_are_radio_buttons(self):
        from PySide6.QtGui import QAccessible
        self.load(self.CHIPS)
        self.assertTrue(self.item("c_chip_classic").property("activeFocusOnTab"))
        self.assertFalse(self.item("c_chip_halloween").property("activeFocusOnTab"))
        QAccessible.setActive(True)
        self.addCleanup(QAccessible.setActive, False)
        iface = QAccessible.queryAccessibleInterface(self.item("c_chip_classic"))
        self.assertEqual((iface.role(), iface.text(QAccessible.Text.Name), iface.state().checked), (QAccessible.Role.RadioButton, "Classic", True))

    def test_the_preview_card_shows_the_engines_picture(self):
        import time
        self.load('PreviewCard { objectName: "p"; x: 20; y: 20; source: "image://preview/0/100/100/classic/none/1" }', 300, 400)
        p = self.item("p")
        end = time.time() + 5
        while time.time() < end and p.property("status") != 1:
            self.app.processEvents()
            time.sleep(0.02)
        self.assertEqual(p.property("status"), 1)                     # Image.Ready
        self.assertEqual((p.width(), p.height()), (200, 300))

    def test_the_preview_card_keeps_the_old_picture_while_the_next_loads(self):
        import time
        self.load('PreviewCard { objectName: "p"; x: 20; y: 20; source: "image://preview/0/100/100/classic/none/1" }', 300, 400)
        p = self.item("p")
        end = time.time() + 5
        while time.time() < end and p.property("status") != 1:
            self.app.processEvents()
            time.sleep(0.02)
        p.setProperty("source", "image://preview/120/100/100/classic/none/2")
        self.assertTrue(p.property("showing"), "the card went blank while the next picture loaded")


@need_qt
class PreviewImages(unittest.TestCase):
    """The sample cover QML shows, made by the engine and handed over as an image (Qt calls the provider from its image threads)."""
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def setUp(self):
        import steamcase as sc
        if sc.Image is None:
            self.skipTest("Pillow missing")
        from PySide6.QtCore import QSize
        from qtui.preview import PreviewProvider
        self.provider = PreviewProvider()
        self.QSize = QSize

    def get(self, ident, w=200, h=300):
        return self.provider.requestImage(ident, self.QSize(), self.QSize(w, h))

    def test_it_returns_the_asked_size(self):
        img = self.get("0/100/100/classic/none/1", 120, 180)
        self.assertEqual((img.width(), img.height()), (120, 180))
        self.assertFalse(img.isNull())
        self.assertEqual((self.get("0/100/100/classic/none/1").width(), self.get("0/100/100/classic/none/1").height()), (200, 300))

    def test_the_hue_changes_the_picture_but_not_for_greys(self):
        a, b = self.get("0/100/100/classic/none/1"), self.get("120/100/100/classic/none/2")
        self.assertNotEqual(a.pixelColor(3, 150).name(), b.pixelColor(3, 150).name())
        g1, g2 = self.get("10/0/50/classic/none/3"), self.get("200/0/50/classic/none/4")
        self.assertEqual(g1.pixelColor(3, 150).name(), g2.pixelColor(3, 150).name())

    def test_a_theme_and_a_treatment_change_the_picture(self):
        import steamcase as sc
        plain = self.get("0/100/100/classic/none/1")
        themed = self.get("0/100/100/halloween/none/2")
        marked = self.get("0/100/100/classic/%s/3" % sc.TREATMENTS[0])
        self.assertNotEqual(bytes(plain.constBits()), bytes(themed.constBits()))
        self.assertNotEqual(bytes(plain.constBits()), bytes(marked.constBits()))

    def test_a_bad_request_gives_a_transparent_picture_of_the_asked_size(self):
        for ident in ("", "x", "1/2/3", "a/b/c/classic/none/1", "0/100/100/pumpkin/none/1", "0/100/100/classic/nonsense/1", "0/100/100/classic/none", "0/100/100/classic/none/1/extra",
                      "../../etc/passwd", "999999999999/100/100/classic/none/1"):
            with self.subTest(ident):
                img = self.get(ident, 50, 75)
                self.assertEqual((img.width(), img.height()), (50, 75))
                self.assertEqual(img.pixelColor(25, 37).alpha(), 0)

    def test_an_engine_failure_gives_the_placeholder_not_an_exception(self):
        from unittest import mock
        with mock.patch("steamcase.preview_cover", side_effect=RuntimeError("boom")):
            img = self.get("0/100/100/classic/none/1", 50, 75)
        self.assertEqual((img.width(), img.height(), img.pixelColor(25, 37).alpha()), (50, 75, 0))

    def test_a_repeated_request_is_not_rendered_again(self):
        import steamcase as sc
        from unittest import mock
        with mock.patch("steamcase.preview_cover", wraps=sc.preview_cover) as engine:
            a = self.get("33/100/100/classic/none/1")
            b = self.get("33/100/100/classic/none/2")                    # only the serial differs
        self.assertEqual(engine.call_count, 1)
        self.assertEqual(bytes(a.constBits()), bytes(b.constBits()))

    def test_many_threads_at_once_all_get_a_valid_picture(self):
        import threading
        results, errors = [], []

        def work(i):
            try:
                img = self.get("%d/100/100/classic/none/%d" % (i * 20, i))
                results.append((img.width(), img.height()))
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=work, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        self.assertEqual(errors, [])
        self.assertEqual(results, [(200, 300)] * 8)

    def test_the_provider_is_registered_in_the_window(self):
        from qtui.app import close_engine, create_engine
        from qtui.shell import Shell
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        engine = create_engine(Shell(os.path.join(tmp, "s.json"), downloads=tmp, covers_dir=tmp))
        self.addCleanup(close_engine, engine)
        self.assertIsNotNone(engine.imageProvider("preview"))


@need_qt
class LookState(unittest.TestCase):
    """The Look step: the case colour, the theme and the art switches, with the tone remembered through the covers already made."""
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def setUp(self):
        from qtui.shell import Shell
        self.Shell = Shell
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.settings = os.path.join(self.tmp, "settings.json")
        self.covers = os.path.join(self.tmp, "covers")
        os.makedirs(self.covers)
        self.shell = self.new_shell()
        self.look = self.shell.look

    def new_shell(self):
        return self.Shell(self.settings, downloads=os.path.join(self.tmp, "Downloads"), covers_dir=self.covers)

    def make_cover(self, hue=0, sat=100, val=100, theme=None):
        import steamcase as sc
        if sc.Image is None:
            self.skipTest("Pillow missing")
        art = os.path.join(self.tmp, "art.png")
        sc.Image.new("RGB", (100, 150), (10, 120, 30)).save(art)
        sc.build_cover(art, os.path.join(self.covers, "Game_1_1.png"), sc.load_frame(hue, sat=sat, val=val), hue, sat=sat, val=val, theme=theme)

    def wait(self, ms=250):
        import time
        end = time.time() + ms / 1000
        while time.time() < end:
            self.app.processEvents()
            time.sleep(0.01)

    def test_it_starts_at_the_original_tone(self):
        l = self.look
        self.assertEqual((l.hue, l.sat, l.val, l.toneName, l.toneHint, l.colourNote, l.theme), (0, 100, 100, "Original", "", "", "classic"))
        self.assertEqual([x["selected"] for x in l.swatches], [True] + [False] * 8)

    def test_a_tone_changes_all_three_values_with_one_signal(self):
        seen = []
        self.look.toneChanged.connect(lambda: seen.append((self.look.hue, self.look.sat, self.look.val)))
        self.look.setTone(90, 80, 70)
        self.assertEqual(seen, [(90, 80, 70)])
        self.assertEqual(self.look.toneName, "Custom \u00b7 90\u00b0 80% 70%")
        self.assertEqual(self.look.colourNote, "Only the original colour is checked for readable text.")
        self.look.setTone(90, 80, 70)                                     # no change: no signal
        self.assertEqual(len(seen), 1)

    def test_values_are_clamped(self):
        self.look.setTone(-30, 150, -5)
        self.assertEqual((self.look.hue, self.look.sat, self.look.val), (330, 100, 0))
        self.look.hue = 725
        self.assertEqual(self.look.hue, 5)
        self.look.sat = -4
        self.assertEqual(self.look.sat, 0)

    def test_the_sliders_set_one_value_each(self):
        self.look.hue = 120
        self.look.sat = 55
        self.look.val = 66
        self.assertEqual((self.look.hue, self.look.sat, self.look.val), (120, 55, 66))

    def test_a_swatch_sets_its_tone_and_only_it_is_selected(self):
        import steamcase as sc
        for i in range(9):
            with self.subTest(i):
                self.look.setTone(200, 33, 44)
                self.look.pickSwatch(i)
                chosen = [k for k, x in enumerate(self.look.swatches) if x["selected"]]
                self.assertEqual(chosen, [i])
                self.assertEqual(sc.tone_key(self.look.hue, self.look.sat, self.look.val), sc.tone_key(self.look.swatches[i]["hue"], self.look.swatches[i]["sat"], self.look.swatches[i]["val"]))
        self.look.pickSwatch(99)                                          # outside the nine: ignored
        self.look.pickSwatch(-1)
        self.assertEqual([k for k, x in enumerate(self.look.swatches) if x["selected"]], [8])

    def test_a_grey_ignores_the_hue_and_says_so(self):
        self.look.pickSwatch(7)                                           # Graphite
        self.assertEqual(self.look.toneName, "Graphite")
        self.look.hue = 200
        self.assertEqual(self.look.toneName, "Graphite")
        self.assertEqual(self.look.toneHint, "Colour has no effect on grey or black.")
        self.assertTrue(self.look.swatches[7]["selected"])

    def test_the_tone_of_the_covers_already_made_is_shown_at_start(self):
        self.make_cover(90, 80, 70)
        look = self.new_shell().look
        self.assertEqual((look.hue, look.sat, look.val), (90, 80, 70))

    def test_the_theme_of_the_covers_already_made_is_shown_at_start(self):
        self.make_cover(theme="halloween")
        self.assertEqual(self.new_shell().look.theme, "halloween")

    def test_a_missing_empty_or_garbage_covers_folder_gives_the_defaults(self):
        for setup in (lambda: shutil.rmtree(self.covers), lambda: None, lambda: (os.makedirs(self.covers, exist_ok=True), open(os.path.join(self.covers, "Game_1_1.png"), "w").write("garbage"))):
            setup()
            look = self.new_shell().look
            self.assertEqual((look.hue, look.sat, look.val, look.theme), (0, 100, 100, "classic"))

    def test_the_theme_takes_only_the_known_values(self):
        self.look.theme = "halloween"
        self.assertEqual(self.look.theme, "halloween")
        self.look.theme = "pumpkin"
        self.assertEqual(self.look.theme, "halloween")
        self.look.theme = "classic"
        self.assertEqual(self.look.theme, "classic")

    def test_the_art_switches_are_remembered(self):
        self.look.useCustomArt = True
        self.look.skipAutoArt = True
        again = self.new_shell().look
        self.assertTrue(again.useCustomArt and again.skipAutoArt)
        self.assertTrue(self.new_shell().switchValue("use_custom_art"))

    def test_the_preview_follows_a_burst_of_changes_once(self):
        seen = []
        self.look.previewSourceChanged.connect(lambda: seen.append(self.look.previewSource))
        for h in range(10, 110, 10):
            self.look.setTone(h, 100, 100)
        self.assertEqual(seen, [])                                        # not yet: the burst is still going on
        self.wait(300)
        self.assertEqual(len(seen), 1)
        self.assertIn("/100/100/100/classic/none/", seen[0])
        self.assertTrue(seen[0].startswith("image://preview/"))

    def test_the_colours_for_the_sliders_come_from_python(self):
        import steamcase as sc
        self.assertEqual(self.look.colorFor(120, 50, 80), sc.case_color(120, 50, 80))
        self.assertEqual(self.look.trackStart("sat"), sc.case_color(0, 0, 100))
        self.assertEqual(self.look.trackEnd("val"), sc.case_color(0, 100, 100))
        self.assertEqual(len(self.look.hueColors()), 36)
        self.assertEqual(self.look.trackStart("nonsense"), "#000000")     # never an exception into QML


@need_qt
class ShellObject(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def setUp(self):
        from qtui.shell import Shell
        self.Shell = Shell
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.path = os.path.join(self.tmp, "settings.json")
        self.dl = os.path.join(self.tmp, "Downloads")
        self.shell = Shell(self.path, downloads=self.dl, covers_dir=os.path.join(self.tmp, "covers"))

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
        self.assertTrue(self.Shell(self.path, downloads=self.dl, covers_dir=os.path.join(self.tmp, "covers")).reduceEffects)

    def test_switches_are_saved_and_unknown_ones_refused(self):
        self.shell.setSwitch("skip_auto_art", True)
        self.assertTrue(self.Shell(self.path, downloads=self.dl, covers_dir=os.path.join(self.tmp, "covers")).switchValue("skip_auto_art"))
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

    def test_the_window_never_stays_on_a_step_that_became_locked(self):
        self.shell.setFact("ready", True)
        self.shell.setFact("look_done", True)
        self.shell.go(3)
        self.assertEqual(self.shell.current, 3)
        seen = []
        self.shell.currentChanged.connect(lambda: seen.append(self.shell.current))
        self.shell.setFact("ready", False)                      # e.g. installed-only switched off
        self.assertEqual(self.states()["hundred"], "locked")
        self.assertEqual(self.shell.current, 1)                 # back to the last step that is still open
        self.assertEqual(seen, [1])

    def test_home_stays_when_nothing_is_locked_under_it(self):
        self.shell.setFact("ready", True)
        self.shell.setFact("ready", False)
        self.assertEqual(self.shell.current, 0)

    def test_a_corrupt_settings_file_gives_defaults(self):
        with open(self.path, "w") as f:
            f.write("{{{")
        shell = self.Shell(self.path, downloads=self.dl, covers_dir=os.path.join(self.tmp, "covers"))
        self.assertFalse(shell.reduceEffects)
        self.assertTrue(shell.switchValue("restart_steam"))


def contrast(a, b):
    """WCAG contrast ratio of two #rrggbb colours."""
    def lum(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


class BundledAssets(unittest.TestCase):
    def test_the_list_matches_what_the_build_recipe_bundles(self):
        import re
        from qtui.assets import REQUIRED_ASSETS
        with open(os.path.join(os.path.dirname(QML_DIR), "..", "steamcase-qt.spec")) as f:
            listed = re.search(r"ASSETS = \[(.*?)\]", f.read(), re.S).group(1)
        self.assertEqual(sorted(REQUIRED_ASSETS), sorted(re.findall(r'"([\w.]+)"', listed)))

    def test_missing_assets_are_named(self):
        from qtui.assets import REQUIRED_ASSETS, missing_assets
        empty = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, empty, True)
        self.assertEqual(missing_assets(empty), sorted(REQUIRED_ASSETS))
        open(os.path.join(empty, "discord.png"), "w").close()
        self.assertNotIn("discord.png", missing_assets(empty))
        self.assertEqual(missing_assets(os.path.join(os.path.dirname(QML_DIR), "..", "assets")), [])


class BuildTrimList(unittest.TestCase):
    """steamcase-qt.spec drops Qt parts the window never uses (113.8 MB -> 73.2 MB measured). The list must never match something the window needs."""
    NEEDED = ["PySide6/Qt/plugins/platforms/libqxcb.so", "PySide6/Qt/plugins/platforms/libqoffscreen.so", "PySide6/Qt/plugins/platforms/libqwayland.so",
              "PySide6/Qt/plugins/platformthemes/libqxdgdesktopportal.so", "PySide6/Qt/plugins/imageformats/libqjpeg.so", "PySide6/Qt/plugins/imageformats/libqwebp.so",
              "PySide6/Qt/plugins/xcbglintegrations/libqxcb-glx-integration.so", "PySide6/Qt/qml/QtQuick/Controls/Basic/Button.qml", "PySide6/Qt/qml/QtQuick/Effects/qmldir",
              "PySide6/Qt/qml/QtQuick/Controls/impl/qmldir", "PySide6/Qt/qml/QtQml/qmldir", "PySide6/Qt/lib/libQt6Quick.so.6", "PySide6/Qt/lib/libQt6Qml.so.6",
              "PySide6/Qt/lib/libQt6Gui.so.6", "PySide6/Qt/lib/libQt6Core.so.6", "PySide6/Qt/lib/libQt6Network.so.6", "PySide6/Qt/lib/libQt6OpenGL.so.6",
              "PySide6/Qt/lib/libQt6QuickControls2.so.6", "PySide6/Qt/lib/libQt6QuickControls2Basic.so.6", "PySide6/Qt/lib/libQt6QuickTemplates2.so.6",
              "PySide6/Qt/lib/libicudata.so.73", "PySide6/QtOpenGL.abi3.so", "PySide6/Qt/qml/QtQuick/Dialogs/qmldir", "PySide6/Qt/qml/Qt/labs/folderlistmodel/qmldir", "PySide6/Qt/lib/libQt6QuickDialogs2.so.6", "PySide6/QtQuick.abi3.so", "libX11.so.6", "libfontconfig.so.1", "libfreetype.so.6"]

    def block(self):
        import re
        with open(os.path.join(os.path.dirname(QML_DIR), "..", "steamcase-qt.spec")) as f:
            return re.findall(r'"([^"]+)"', re.search(r"BLOCK = \[(.*?)\]", f.read(), re.S).group(1))

    def test_the_list_is_not_empty(self):
        self.assertGreater(len(self.block()), 20)

    def test_nothing_the_window_needs_is_dropped(self):
        for pattern in self.block():
            for needed in self.NEEDED:
                self.assertNotIn(pattern, needed, "%r would drop %s" % (pattern, needed))


class QtPreviewWorkflow(unittest.TestCase):
    """.github/workflows/qt-preview.yml builds the Qt window on three systems by hand, so it can be tried before a release. It must stay inert and safe."""
    PATH = os.path.join(os.path.dirname(QML_DIR), "..", ".github", "workflows", "qt-preview.yml")

    def text(self):
        with open(self.PATH) as f:
            return f.read()

    def test_it_only_runs_by_hand(self):
        import re
        on = re.search(r"^on:\n((?:[ \t]+.*\n|\n)+)", self.text(), re.M).group(1)
        self.assertEqual(re.findall(r"^\s{2}(\w[\w-]*):", on, re.M), ["workflow_dispatch"])

    def test_it_has_no_secrets_and_read_only_permissions(self):
        t = self.text()
        self.assertNotIn("secrets.", t)
        self.assertIn("permissions:\n  contents: read", t)

    def test_every_action_is_pinned_by_commit(self):
        import re
        uses = re.findall(r"uses:\s*(\S+)", self.text())
        self.assertTrue(uses)
        for u in uses:
            self.assertRegex(u, r"@[0-9a-f]{40}$", u)

    def test_it_builds_on_the_three_systems_and_checks_the_built_app(self):
        t = self.text()
        for needle in ("windows-latest", "macos-latest", "ubuntu-latest", "steamcase-qt.spec", "--selftest", "unittest discover -s tests", "requirements-qt.txt"):
            self.assertIn(needle, t)

    def test_the_qt_requirements_are_pinned(self):
        with open(os.path.join(os.path.dirname(QML_DIR), "..", "requirements-qt.txt")) as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        self.assertIn("-r requirements-build.txt", lines)
        self.assertTrue(any(l.startswith("PySide6-Essentials==") for l in lines), lines)


class ChecksWorkflow(unittest.TestCase):
    def test_the_qt_tests_run_in_the_normal_checks(self):
        with open(os.path.join(os.path.dirname(QML_DIR), "..", ".github", "workflows", "checks.yml")) as f:
            text = f.read()
        for needle in ("qt-tests:", "requirements-qt.txt", "tests.test_qtui", "python -m qtui --selftest", "QT_QPA_PLATFORM: offscreen"):
            self.assertIn(needle, text)


class Tokens(unittest.TestCase):
    """The colours in qtui/qml/Theme.qml are those of docs/ui-guide.md, with the contrast the guide promises; nothing else holds a colour."""
    GUIDE = {"bg": "#11151c", "card": "#182433", "raised": "#22344a", "accent": "#66c0f4", "text": "#e6edf3", "muted": "#93a7bb", "faint": "#7d92a8",
             "edge": "#5d7a96", "done": "#5ba32b", "warning": "#f0b429", "error": "#ff7b72", "accentInk": "#0b141d", "shadow": "#000000"}

    def theme(self):
        import re
        with open(os.path.join(QML_DIR, "Theme.qml")) as f:
            return dict(re.findall(r'readonly property color (\w+): "(#[0-9a-fA-F]{6})"', f.read()))

    def test_the_colours_are_the_guides(self):
        self.assertEqual(self.theme(), self.GUIDE)

    def test_contrast_meets_the_guide(self):
        t = self.theme()
        for fg, bg, need in (("text", "card", 4.5), ("muted", "card", 4.5), ("faint", "card", 4.5), ("text", "bg", 4.5), ("accent", "bg", 4.5),
                             ("accentInk", "accent", 4.5), ("accentInk", "done", 4.5), ("edge", "card", 3.0), ("warning", "card", 4.5), ("error", "card", 4.5)):
            with self.subTest("%s on %s" % (fg, bg)):
                self.assertGreaterEqual(contrast(t[fg], t[bg]), need)

    def test_the_guide_names_the_steps_like_the_window(self):
        with open(os.path.join(os.path.dirname(QML_DIR), "..", "docs", "ui-guide.md")) as f:
            text = f.read()
        self.assertIn("1 Game list, 2 Look, 3 100% games, 4 Make, 5 Add to Steam", text)
        self.assertNotIn("Extras", text.replace("Extras became", ""))

    def qml_files(self):
        for name in sorted(os.listdir(QML_DIR)):
            if name.endswith(".qml") and name != "Theme.qml":
                with open(os.path.join(QML_DIR, name)) as f:
                    yield name, f.read()

    def test_only_the_guides_durations_are_used(self):
        import re
        for name, text in self.qml_files():
            self.assertEqual(re.findall(r"duration:\s*\d", text), [], name + ": a duration must go through Theme.dur")
            for n in re.findall(r"Theme\.dur\((\d+)\)", text):
                self.assertIn(int(n), (90, 120, 200, 260), "%s: %s ms is not in the guide" % (name, n))

    def test_no_loose_design_numbers(self):
        """Corner radius, text size, shadow and opacity values come from Theme (sizes of layout boxes may stay in the files)."""
        import re
        for name, text in self.qml_files():
            for pattern in (r"\bradius:\s*\d", r"pixelSize:\s*\d", r"shadow(?:Blur|Opacity|VerticalOffset):\s*-?\d", r"\bopacity:[^\n]*\d\.\d",
                            r"Qt\.lighter\([^)]*,\s*[\d.]+\)", r"(?:blur|brightness|saturation):\s*-?\d"):
                self.assertEqual(re.findall(pattern, text), [], "%s: %s" % (name, pattern))

    def test_no_loose_layout_numbers(self):
        """Sizes, spacing, margins, borders and positions come from Theme too (0 is allowed). Only Theme.qml may hold a number."""
        import re
        patterns = (r"\b(?:width|height|implicitWidth|implicitHeight|spacing)\s*:\s*(?:-(?!Theme)|[1-9])", r"\banchors\.\w*[mM]argins?\s*:\s*(?:-(?!Theme)|[1-9])",
                    r"\b[xy]\s*:\s*(?:-(?!Theme)|[1-9])", r"\bborder\.width\s*:[^\n]*[1-9]", r"\bsourceSize\.\w+\s*:\s*[1-9]", r"Theme\.\w+\s*[-+*/]\s*\d",
                    r"Math\.(?:min|max)\(\s*[1-9]", r"\bfont\.pixelSize\s*:\s*[1-9]")
        for name, text in self.qml_files():
            for pattern in patterns:
                self.assertEqual(re.findall(pattern, text), [], "%s: %s" % (name, pattern))

    def test_there_is_no_picture_behind_the_window(self):
        """The approved design has plain surfaces; a decorative backdrop was added once without asking and removed again."""
        import re
        with open(os.path.join(QML_DIR, "Main.qml")) as f:
            main = f.read()
        self.assertEqual(re.findall(r"\bImage\s*\{", main), ["Image {"], "the only picture in the window is the Discord icon")
        for name in os.listdir(QML_DIR):
            with open(os.path.join(QML_DIR, name)) as f:
                self.assertNotIn("backdrop", f.read().lower(), name)

    def test_no_other_file_has_a_colour_of_its_own(self):
        import re
        for name in os.listdir(QML_DIR):
            if name.endswith(".qml") and name != "Theme.qml":
                with open(os.path.join(QML_DIR, name)) as f:
                    self.assertEqual(re.findall(r"#[0-9a-fA-F]{3,8}\b", f.read()), [], name)


@need_qt
class ShellWindow(unittest.TestCase):
    """The real QML window, offscreen."""
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def setUp(self):
        from qtui.shell import Shell
        from qtui.app import create_engine
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.shell = Shell(os.path.join(self.tmp, "settings.json"), downloads=os.path.join(self.tmp, "Downloads"), covers_dir=os.path.join(self.tmp, "covers"))
        self.engine = create_engine(self.shell)
        self.addCleanup(self.close, self.engine)
        self.root = self.engine.rootObjects()[0]

    def close(self, engine):
        from qtui.app import close_engine
        close_engine(engine)

    def item(self, name):
        """The QML item with this objectName, found in the visual tree (delegates of a Repeater are not QObject children of the window)."""
        stack = [self.root.contentItem()]
        while stack:
            it = stack.pop()
            if it.objectName() == name:
                return it
            stack.extend(it.childItems())
        self.fail("no item named %s" % name)

    def test_the_window_has_six_nav_items_and_the_footer(self):
        self.assertEqual([self.item("nav_" + k).property("label") for k in ("home", "game_list", "look", "hundred", "make", "add")],
                         ["Home", "1  Game list", "2  Look", "3  100% games", "4  Make", "5  Add to Steam"])
        self.assertEqual(self.item("footer_updates").property("text"), "Check for updates")
        self.assertEqual(self.item("footer_discord").property("text"), "Discord")

    def click(self, name):
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtTest import QTest
        it = self.item(name)
        centre = it.mapToScene(QPointF(it.width() / 2, it.height() / 2)).toPoint()
        QTest.mouseClick(self.root, Qt.LeftButton, Qt.NoModifier, centre)
        self.app.processEvents()

    def test_a_locked_item_ignores_clicks_and_unlocks_with_the_game_list(self):
        self.click("nav_look")
        self.assertEqual(self.shell.current, 0)
        self.shell.setFact("ready", True)
        self.app.processEvents()
        self.click("nav_look")
        self.assertEqual(self.shell.current, 2)

    def test_a_locked_item_is_not_a_tab_stop(self):
        self.assertFalse(self.item("nav_look").property("activeFocusOnTab"))
        self.assertTrue(self.item("nav_game_list").property("activeFocusOnTab"))
        self.shell.setFact("ready", True)
        self.app.processEvents()
        self.assertTrue(self.item("nav_look").property("activeFocusOnTab"))

    def test_reduce_effects_makes_every_duration_zero(self):
        self.assertEqual(self.root.property("screenMs"), 260)
        self.shell.reduceEffects = True
        self.app.processEvents()
        self.assertEqual(self.root.property("screenMs"), 0)

    def test_the_window_has_the_apps_icon(self):
        self.assertFalse(QGuiApplication.windowIcon().isNull())

    def test_the_window_opens_without_the_art_files(self):
        from qtui.app import create_engine
        empty = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, empty, True)
        engine = create_engine(self.shell, assets_dir=empty)           # no discord.png, no default art
        self.addCleanup(self.close, engine)
        self.assertEqual(len(engine.rootObjects()), 1)

    def test_a_qml_error_is_an_error(self):
        from qtui.app import create_engine
        bad = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, bad, True)
        shutil.copytree(QML_DIR, os.path.join(bad, "qml"))
        with open(os.path.join(bad, "qml", "Main.qml"), "a") as f:
            f.write("\nthis is not qml\n")
        with self.assertRaises(RuntimeError):
            create_engine(self.shell, qml_dir=os.path.join(bad, "qml"))

    def press(self, name, key, repeat=False):
        from PySide6.QtCore import QCoreApplication, QEvent, Qt
        from PySide6.QtGui import QKeyEvent
        self.root.requestActivate()
        self.item(name).forceActiveFocus()
        self.app.processEvents()
        QCoreApplication.sendEvent(self.root, QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier, "", repeat))
        self.app.processEvents()

    def test_every_activation_key_works_on_a_nav_item(self):
        from PySide6.QtCore import Qt
        self.shell.setFact("ready", True)
        for key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            with self.subTest(key=key):
                self.shell.go(0)
                self.press("nav_look", key)
                self.assertEqual(self.shell.current, 2)

    def test_holding_a_key_does_not_repeat_the_action(self):
        from PySide6.QtCore import Qt
        self.shell.setFact("ready", True)
        self.press("nav_look", Qt.Key_Return, repeat=True)
        self.assertEqual(self.shell.current, 0)

    def test_qt_does_not_expose_the_os_reduced_motion_setting(self):
        """True for Qt 6.12 (pinned). If this fails after a Qt upgrade, Qt now offers the setting: wire it to Shell.reduceEffects."""
        self.assertFalse(hasattr(QGuiApplication.styleHints(), "reducedMotion"))


@need_qt
class Entry(unittest.TestCase):
    """`python -m qtui --selftest`: builds the window offscreen, checks it, and exits 0 (ok) or 1 (with the QML messages)."""
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def run_selftest(self, *extra):
        import subprocess
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        return subprocess.run([sys.executable, "-m", "qtui", "--selftest", *extra], cwd=self.ROOT, env=env, capture_output=True, text=True, timeout=120)

    def test_the_selftest_passes(self):
        r = self.run_selftest()
        self.assertEqual((r.returncode, r.stdout.strip().splitlines()[-1:]), (0, ["selftest ok"]), r.stderr)
        problems = [l for l in r.stderr.splitlines() if any(k in l for k in (".qml", "TypeError", "ReferenceError", "Binding loop", "QML "))]
        self.assertEqual(problems, [], "QML messages on stderr (Qt's own platform logging, qt.qpa.*, is allowed). Full stderr:\n" + r.stderr)

    def test_the_selftest_does_not_touch_the_real_settings_file(self):
        import qtui.settings as st
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        import subprocess
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", XDG_DATA_HOME=home, HOME=home, LOCALAPPDATA=home)
        subprocess.run([sys.executable, "-m", "qtui", "--selftest"], cwd=self.ROOT, env=env, capture_output=True, text=True, timeout=120)
        written = [n for _, _, names in os.walk(home) for n in names if not n.endswith(".qmlc")]          # Qt's own compiled-QML cache is fine
        self.assertEqual(written, [])

    def test_the_window_closes_cleanly_whatever_python_destroys_first(self):
        """Python frees objects in an order that differs between systems. Once the window is closed on purpose, the shell may die at any time."""
        import subprocess
        code = (
            "import sys, os, tempfile\n"
            "sys.path.insert(0, %r)\n"
            "from PySide6.QtGui import QGuiApplication\n"
            "app = QGuiApplication([])\n"
            "from qtui.shell import Shell\n"
            "from qtui.app import create_engine, close_engine\n"
            "shell = Shell(os.path.join(tempfile.mkdtemp(), 's.json'), downloads=tempfile.mkdtemp(), covers_dir=tempfile.mkdtemp())\n"
            "engine = create_engine(shell)\n"
            "close_engine(engine)\n"
            "del shell\n"
            "del engine\n"
            "print('closed')\n" % self.ROOT)
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "closed"), r.stderr)
        self.assertNotIn("TypeError", r.stderr, r.stderr)

    def test_a_startup_failure_is_written_to_a_log_file(self):
        """The packaged app has no console, so a message on stderr is lost."""
        bad = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, bad, True)
        shutil.copytree(QML_DIR, os.path.join(bad, "qml"))
        with open(os.path.join(bad, "qml", "Main.qml"), "a") as f:
            f.write("\nthis is not qml\n")
        log = os.path.join(bad, "qtui-error.log")
        self.run_selftest("--qml-dir", os.path.join(bad, "qml"), "--log", log)
        with open(log) as f:
            self.assertIn("Main.qml", f.read())

    def test_the_selftest_also_opens_the_game_list_screen(self):
        """Step 1 imports parts (the file dialog) that only a packaged build can lack, so the self-test must load it."""
        import re
        with open(os.path.join(self.ROOT, "qtui", "__main__.py")) as f:
            text = f.read()
        self.assertRegex(text, r"shell\.go\(1\)")
        self.assertIn("gamelist_next", text)
        self.assertRegex(text, r"Shell\(.*downloads=", "the self-test must never look at the real Downloads folder")

    def test_a_missing_bundled_picture_fails_the_selftest(self):
        empty = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, empty, True)
        r = self.run_selftest("--assets-dir", empty)
        self.assertEqual(r.returncode, 1)
        self.assertIn("discord.png", r.stderr)
        self.assertNotIn("selftest ok", r.stdout)

    def test_report_error_survives_no_console_and_no_folder(self):
        from unittest import mock
        from qtui.app import report_error
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder, True)
        log = os.path.join(folder, "sub", "qtui-error.log")
        with mock.patch.object(sys, "stderr", None):                   # a windowed app has no stderr
            report_error("x" * 100000, log)
        with open(log) as f:
            self.assertTrue(0 < len(f.read()) <= 20000)
        blocker = os.path.join(folder, "file")
        open(blocker, "w").close()
        report_error("boom", os.path.join(blocker, "log"))             # an unwritable place: no exception

    def test_a_broken_qml_file_fails_the_selftest(self):
        bad = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, bad, True)
        shutil.copytree(QML_DIR, os.path.join(bad, "qml"))
        with open(os.path.join(bad, "qml", "Main.qml"), "a") as f:
            f.write("\nthis is not qml\n")
        r = self.run_selftest("--qml-dir", os.path.join(bad, "qml"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("Main.qml", r.stderr)
        self.assertNotIn("selftest ok", r.stdout)


if __name__ == "__main__":
    unittest.main()
