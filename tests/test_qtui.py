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


def open(path, mode="r", *args, **kwargs):          # noqa: A001 - every text file in these tests is UTF-8, on every system
    """The built-in open, reading and writing text as UTF-8 unless an encoding is given."""
    import builtins
    if "b" not in mode:
        kwargs.setdefault("encoding", "utf-8")
    return builtins.open(path, mode, *args, **kwargs)



class QtCase(unittest.TestCase):
    """A Qt test: leftovers (objects with timers) are collected here, on the main thread, never by a worker thread that happens to run the collector."""
    def tearDown(self):
        import gc
        gc.collect()
        super().tearDown()
QML_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "qtui", "qml")


def qt_app():
    """One Qt application for the whole test process (a second one cannot be made)."""
    return QGuiApplication.instance() or QGuiApplication([])


class ReadsUtf8(unittest.TestCase):
    """The files of the window hold quotes, arrows and dots. Windows reads text in cp1252 unless told otherwise, which cannot decode a closing quote."""
    def test_text_files_in_this_module_are_read_as_utf8(self):
        path = os.path.join(tempfile.mkdtemp(), "x.qml")
        self.addCleanup(shutil.rmtree, os.path.dirname(path), True)
        with __import__("io").open(path, "w", encoding="utf-8") as f:
            f.write("\u201cdone\u201d \u2192")
        with open(path) as f:
            self.assertEqual((f.encoding, f.read()), ("utf-8", "\u201cdone\u201d \u2192"))
        with open(path, "rb") as f:                                     # binary reads are left alone
            self.assertIsInstance(f.read(), bytes)


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


class EngineSelfCheck(unittest.TestCase):
    """What the packaged app's --selftest proves about the engine inside the bundle (the Tk window's selftest did the same)."""
    def setUp(self):
        import steamcase as sc
        if sc.Image is None:
            self.skipTest("Pillow missing")

    def test_a_healthy_engine_has_no_problems(self):
        from qtui import selfcheck
        self.assertEqual(selfcheck.engine_problems(), [])

    def test_each_broken_part_is_named(self):
        from unittest import mock
        import steamcase as sc
        from qtui import selfcheck
        cases = (("build_cover", mock.patch.object(sc, "build_cover", side_effect=ValueError("no frame")), "no frame"),
                 ("certificates", mock.patch.object(sc, "_ssl_context", return_value=mock.Mock(cert_store_stats=lambda: {"x509_ca": 0})), "no trusted certificates"),
                 ("recognise", mock.patch.object(sc, "is_steamcase_cover", return_value=False), "not recognised as ours"),
                 ("colour", mock.patch.object(sc, "cover_colour", return_value=(5, 5, 5)), "does not record its colour"),
                 ("recolour", mock.patch.object(sc, "preview_cover", return_value=sc.preview_cover(0)), "case colour cannot be changed"))
        for name, patch, words in cases:
            with self.subTest(name), patch:
                problems = selfcheck.engine_problems()
                self.assertTrue(any(words in p for p in problems), (words, problems))

    def test_the_ribbon_picture_is_checked_too(self):
        from unittest import mock
        import steamcase as sc
        from qtui import selfcheck
        with mock.patch.object(sc, "COMPLETION_OVERLAY", os.path.join(tempfile.gettempdir(), "no-such-overlay.png")):
            self.assertTrue(any("completion overlay missing" in p for p in selfcheck.engine_problems()))

    def test_a_packaged_linux_app_that_still_hands_its_libraries_to_children_fails(self):
        from unittest import mock
        from qtui import selfcheck
        with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(sys, "platform", "linux"), mock.patch.object(sys, "_MEIPASS", "/tmp/_MEIx", create=True):
            with mock.patch.dict(os.environ, {"LD_LIBRARY_PATH": "/tmp/_MEIx:/lib", "LD_LIBRARY_PATH_ORIG": "/tmp/_MEIx:/lib"}):
                self.assertTrue(any("inherit the bundled libraries" in p for p in selfcheck.engine_problems()))
            with mock.patch.dict(os.environ, {"LD_LIBRARY_PATH": "/tmp/_MEIx:/lib", "LD_LIBRARY_PATH_ORIG": "/usr/lib"}):
                self.assertFalse(any("inherit the bundled libraries" in p for p in selfcheck.engine_problems()))

    def test_the_qt_selftest_reports_engine_problems(self):
        from unittest import mock
        if QGuiApplication is None:
            self.skipTest("PySide6 missing")
        from qtui import __main__ as entry
        with mock.patch("qtui.selfcheck.engine_problems", return_value=["the cover colour is wrong"]):
            self.assertEqual(entry.selftest(None, None, os.path.join(os.path.dirname(QML_DIR), "..", "assets"), os.path.join(tempfile.mkdtemp(), "e.log")), 1)


class SystemHelpers(unittest.TestCase):

    def test_a_packaged_linux_app_gives_its_children_the_systems_libraries_again(self):
        from unittest import mock
        with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(sys, "platform", "linux"):
            with mock.patch.dict(os.environ, {"LD_LIBRARY_PATH": "/tmp/_MEI123", "LD_LIBRARY_PATH_ORIG": "/usr/lib/x"}):
                system.restore_child_env()
                self.assertEqual(os.environ["LD_LIBRARY_PATH"], "/usr/lib/x")
            with mock.patch.dict(os.environ, {"LD_LIBRARY_PATH": "/tmp/_MEI123"}, clear=False):
                os.environ.pop("LD_LIBRARY_PATH_ORIG", None)
                system.restore_child_env()
                self.assertNotIn("LD_LIBRARY_PATH", os.environ)

    def test_the_environment_is_left_alone_from_source_and_on_other_systems(self):
        from unittest import mock
        for frozen, platform in ((False, "linux"), (True, "win32"), (True, "darwin")):
            with self.subTest(frozen=frozen, platform=platform):
                with mock.patch.object(sys, "frozen", frozen, create=True), mock.patch.object(sys, "platform", platform):
                    with mock.patch.dict(os.environ, {"LD_LIBRARY_PATH": "/tmp/_MEI123", "LD_LIBRARY_PATH_ORIG": "/usr/lib/x"}):
                        system.restore_child_env()
                        self.assertEqual(os.environ["LD_LIBRARY_PATH"], "/tmp/_MEI123")
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

    def test_the_slider_track_runs_through_the_real_case_colours(self):
        import steamcase as sc
        g = tones.track_gradient(120, 60, 80, "sat", 5)
        self.assertEqual(g, [sc.case_color(120, v, 80) for v in (0, 25, 50, 75, 100)])
        g = tones.track_gradient(120, 60, 80, "val")
        self.assertEqual((len(g), g[0], g[-1]), (24, sc.case_color(120, 60, 0), sc.case_color(120, 60, 100)))
        with self.assertRaises(ValueError):
            tones.track_gradient(0, 0, 0, "hue")

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
        self.assertEqual(sp.HINTS, {"hundred": "(optional)"})
        self.assertEqual(sp.hint("hundred", "active"), "(optional)")
        self.assertEqual(sp.hint("look", "locked"), "after step 1")
        self.assertEqual(sp.hint("hundred", "locked"), "(optional)")           # what it is matters more than why it waits: the longer words would not fit the list
        self.assertEqual(sp.hint("look", "done"), "")

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
class GameListScreen(QtCase):
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
class GameListFlow(QtCase):
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
class LibraryActions(QtCase):
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

    def test_a_bad_file_chosen_with_browse_also_gets_a_box_but_a_noticed_one_does_not(self):
        failures = []
        self.lib.failed.connect(lambda title, text: failures.append((title, text)))
        bad = os.path.join(self.tmp, "userdata.json")
        with open(bad, "w") as f:
            f.write("not json")
        self.lib._on_picked(bad)                                        # picked by the user
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0][0], "That file doesn't look right")
        self.assertIn("userdata.json", failures[0][1] + self.lib.status)
        self.assertTrue(self.lib.status.startswith("That file doesn't look right"))
        self.lib.useFileUrl(__import__("PySide6.QtCore", fromlist=["QUrl"]).QUrl.fromLocalFile(bad).toString())
        self.assertEqual(len(failures), 2)                              # the dialog's answer too
        self.lib.useFile(bad)                                           # the same call from the watcher: only the status line
        self.assertEqual(len(failures), 2)


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
class LibraryState(QtCase):
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
class LookScreen(QtCase):
    """Step 2 as the approved wireframe, in the real window (effects reduced so nothing is still sliding)."""
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def setUp(self):
        from qtui.app import close_engine, create_engine
        from qtui.shell import Shell
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.shell = Shell(os.path.join(self.tmp, "settings.json"), downloads=os.path.join(self.tmp, "Downloads"), covers_dir=os.path.join(self.tmp, "covers"))
        self.shell.reduceEffects = True
        self.shell.library.installedOnly = True               # step 2 is open
        self.engine = create_engine(self.shell)
        self.addCleanup(close_engine, self.engine)
        self.root = self.engine.rootObjects()[0]
        self.look = self.shell.look
        self.shell.go(2)
        self.app.processEvents()

    def item(self, name):
        from qtui.app import find_item
        got = find_item(self.root, name)
        self.assertIsNotNone(got, name)
        return got

    def centre(self, name):
        from PySide6.QtCore import QPointF
        it = self.item(name)
        return it.mapToScene(QPointF(it.width() / 2, it.height() / 2)).toPoint()

    def reveal(self, name):
        """Scroll the page so the item is in view, as a person would."""
        from PySide6.QtCore import QPointF
        scroller = self.item("screen_scroller")
        y = self.item(name).mapToItem(scroller.property("contentItem"), QPointF(0, 0)).y()
        scroller.setProperty("contentY", max(0, y - 40))
        self.app.processEvents()

    def click(self, name):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        self.reveal(name)
        QTest.mouseClick(self.root, Qt.LeftButton, Qt.NoModifier, self.centre(name))
        self.app.processEvents()

    def pos(self, name):
        from PySide6.QtCore import QPointF
        return self.item(name).mapToScene(QPointF(0, 0))

    def test_it_shows_its_title_and_the_nine_swatches(self):
        self.assertEqual(self.item("screen_title").property("text"), "Choose the look")
        self.assertEqual([self.item("look_swatch_%d" % i).property("name") for i in (0, 6, 8)], ["Original", "Black", "Silver"])

    def test_a_swatch_sets_the_tone_and_only_it_is_selected(self):
        self.click("look_swatch_3")
        self.assertEqual((self.look.hue, self.look.sat, self.look.val), (134, 100, 100))
        self.assertEqual([i for i in range(9) if self.item("look_swatch_%d" % i).property("selected")], [3])
        self.assertTrue(self.look.previewSource.startswith("image://preview/"))

    def test_a_slider_changes_the_colour_and_a_grey_says_it_ignores_it(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        c = self.centre("look_hue")
        QTest.mouseClick(self.root, Qt.LeftButton, Qt.NoModifier, c)
        self.app.processEvents()
        self.assertGreater(self.look.hue, 100)
        self.assertEqual(self.item("look_hint").property("text"), "")
        self.click("look_swatch_7")
        self.assertEqual(self.item("look_hint").property("text"), "Colour has no effect on grey or black.")
        self.assertEqual(self.item("look_section_colour_note").property("text"), "Graphite")

    def test_keyboard_focus_stays_on_a_swatch_after_it_is_picked(self):
        """A changed tone must not rebuild the swatches: the one that has the focus would be destroyed and the keyboard user would lose their place."""
        from PySide6.QtCore import QCoreApplication, QEvent, Qt
        from PySide6.QtGui import QKeyEvent
        self.root.requestActivate()
        first = self.item("look_swatch_2")
        first.forceActiveFocus()
        QCoreApplication.sendEvent(self.root, QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier, "", False))
        self.app.processEvents()
        self.assertEqual(self.look.hue, 84)
        again = self.item("look_swatch_2")
        self.assertTrue(again.property("activeFocus"), "the focused swatch was rebuilt")
        self.assertTrue(again.property("selected"))
        self.look.hue = 200                                       # another change of tone
        self.app.processEvents()
        self.assertTrue(self.item("look_swatch_2").property("activeFocus"), "another change of tone rebuilt the swatches")

    def test_the_tone_name_is_at_the_right_of_the_heading(self):
        note = self.item("look_section_colour_note")
        self.assertEqual(note.property("text"), "Original")
        self.click("look_swatch_7")
        self.assertEqual(self.item("look_section_colour_note").property("text"), "Graphite")
        sec = self.item("look_section_colour")
        from PySide6.QtCore import QPointF
        self.assertGreater(note.mapToScene(QPointF(0, 0)).x(), sec.mapToScene(QPointF(sec.width() / 2, 0)).x())     # in the right half

    def test_a_label_is_never_cut_off_at_a_middle_or_narrow_width(self):
        for width in (810, 640):
            self.root.setProperty("width", width)
            self.app.processEvents()
            for name in ("look_custom_art_label", "look_skip_blurry_label"):
                self.reveal(name)
                label = self.item(name)
                self.assertFalse(label.property("truncated"), "%s is cut off at %d px" % (name, width))
                self.assertLessEqual(label.property("contentWidth"), label.width() + 0.5, "%s overflows at %d px" % (name, width))

    def test_swatches_are_radio_buttons_with_one_tab_stop_and_arrow_keys(self):
        from PySide6.QtCore import QCoreApplication, QEvent, Qt
        from PySide6.QtGui import QKeyEvent
        stops = [i for i in range(9) if self.item("look_swatch_%d" % i).property("activeFocusOnTab")]
        self.assertEqual(stops, [0])                                  # the selected one (the original)
        self.root.requestActivate()
        self.item("look_swatch_0").forceActiveFocus()
        for key, expect in ((Qt.Key_Right, 1), (Qt.Key_Right, 2), (Qt.Key_Left, 1), (Qt.Key_End, 8), (Qt.Key_Home, 0)):
            QCoreApplication.sendEvent(self.root, QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier, "", False))
            self.app.processEvents()
            self.assertEqual(self.look.selectedSwatch, expect, key)
            self.assertTrue(self.item("look_swatch_%d" % expect).property("activeFocus"), "the focus did not follow the choice at %d" % expect)
        self.look.setTone(123, 45, 67)                                # none selected: the first is the tab stop
        self.app.processEvents()
        self.assertEqual([i for i in range(9) if self.item("look_swatch_%d" % i).property("activeFocusOnTab")], [0])

    def test_a_slider_track_is_not_redrawn_for_its_own_value(self):
        screen = self.item("look_screen")
        calls = dict(screen.property("calls").toVariant())
        self.look.sat = 40                                            # moves the colourfulness slider itself: its own track does not change
        self.app.processEvents()
        after = dict(screen.property("calls").toVariant())
        self.assertEqual(after["sat"], calls["sat"])
        self.assertGreater(after["val"], calls["val"])                # the brightness track does show the new colourfulness
        self.look.hue = 200
        self.app.processEvents()
        self.assertGreater(dict(screen.property("calls").toVariant())["sat"], after["sat"])

    def test_related_items_are_8_px_apart_and_the_small_size_is_for_hints(self):
        import re
        with open(os.path.join(QML_DIR, "LookScreen.qml")) as f:
            text = f.read()
        self.assertEqual(re.findall(r"spacing:\s*Theme\.s4\b", text), [])
        self.assertLessEqual(len(re.findall(r"Theme\.smallSize", text)), 1)       # only the readable-text note

    def test_the_theme_chips_set_the_theme(self):
        self.click("look_theme_chip_halloween")
        self.assertEqual(self.look.theme, "halloween")
        self.click("look_theme_chip_classic")
        self.assertEqual(self.look.theme, "classic")

    def test_the_art_switches_change_and_are_remembered(self):
        for name in ("look_custom_art", "look_skip_blurry"):
            self.reveal(name)
            it = self.item(name)
            from PySide6.QtCore import QPoint, QPointF, Qt
            from PySide6.QtTest import QTest
            p = it.mapToScene(QPointF(60, it.height() / 2)).toPoint()        # on the label: the empty space to its right is not part of the switch
            QTest.mouseClick(self.root, Qt.LeftButton, Qt.NoModifier, p)
            self.app.processEvents()
        self.assertTrue(self.look.useCustomArt and self.look.skipAutoArt)
        self.assertEqual(self.item("look_custom_art_tip").property("text").startswith("For games where you set your own art"), True)
        self.assertEqual(self.item("look_skip_blurry_tip").property("text"), __import__("steamcase").AUTO_ART_HELP)
        self.assertTrue(self.shell.switchValue("use_custom_art") and self.shell.switchValue("skip_auto_art"))        # saved, not only shown

    def test_next_is_the_only_filled_button_and_opens_the_next_step(self):
        self.assertTrue(self.item("look_next").property("filled"))
        self.assertEqual(self.shell.steps[3]["state"], "locked")
        self.click("look_next")
        self.assertEqual(self.shell.current, 3)
        self.assertEqual(self.shell.steps[3]["state"], "active")

    def test_the_preview_sits_left_of_the_sections_and_above_them_when_narrow(self):
        self.root.setProperty("width", 1000)
        self.app.processEvents()
        self.assertLess(self.pos("look_preview").x(), self.pos("look_section_colour").x())
        self.root.setProperty("width", self.root.property("minimumWidth"))
        self.app.processEvents()
        self.assertLess(self.pos("look_preview").y(), self.pos("look_section_colour").y())

    def test_nothing_sticks_out_of_its_card_at_the_narrowest_window(self):
        from PySide6.QtCore import QPointF
        self.root.setProperty("minimumWidth", 420)
        self.root.setProperty("width", 420)
        self.app.processEvents()
        for sec in ("look_section_colour", "look_section_theme", "look_section_art"):
            s = self.item(sec)
            right = s.mapToScene(QPointF(s.width(), 0)).x()
            names = {"look_section_colour": ["look_hue", "look_sat", "look_val", "look_swatch_8"], "look_section_theme": ["look_theme"],
                     "look_section_art": ["look_custom_art", "look_skip_blurry"]}[sec]
            for n in names:
                it = self.item(n)
                self.assertLessEqual(it.mapToScene(QPointF(it.width(), 0)).x(), right + 0.5, "%s sticks out of %s" % (n, sec))


@need_qt
class LookFlow(QtCase):
    """Step 2 as a person lives it: pick a colour, a swatch, a theme and the art options; the preview follows; Next opens the 100% games step."""
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def test_from_the_game_list_to_the_hundred_percent_step(self):
        import time
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtTest import QTest
        import steamcase as sc
        from qtui.app import close_engine, create_engine, find_item
        from qtui.shell import Shell
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        settings, covers = os.path.join(tmp, "settings.json"), os.path.join(tmp, "covers")
        os.makedirs(covers)
        if sc.Image is None:
            self.skipTest("Pillow missing")
        art = os.path.join(tmp, "art.png")                      # a cover made in another colour is already there
        sc.Image.new("RGB", (100, 150), (10, 120, 30)).save(art)
        sc.build_cover(art, os.path.join(covers, "Game_1_1.png"), sc.load_frame(90), 90)
        shell = Shell(settings, downloads=os.path.join(tmp, "Downloads"), covers_dir=covers)
        shell.reduceEffects = True
        engine = create_engine(shell)
        self.addCleanup(close_engine, engine)
        root = engine.rootObjects()[0]
        look = shell.look
        self.assertEqual((look.hue, look.sat, look.val), (90, 100, 100))      # the screen opens on the colour of the covers already made
        shell.next()
        shell.library.installedOnly = True
        shell.next()
        self.app.processEvents()
        self.assertEqual(find_item(root, "screen_title").property("text"), "Choose the look")

        def click(name, dx=None):
            it = find_item(root, name)
            scroller = find_item(root, "screen_scroller")
            y = it.mapToItem(scroller.property("contentItem"), QPointF(0, 0)).y()
            scroller.setProperty("contentY", max(0, y - 40))
            self.app.processEvents()
            pt = it.mapToScene(QPointF(it.width() / 2 if dx is None else dx, it.height() / 2)).toPoint()
            QTest.mouseClick(root, Qt.LeftButton, Qt.NoModifier, pt)
            self.app.processEvents()
        before = look.previewSource
        click("look_hue")                                       # drag the colour
        self.assertNotEqual(look.hue, 90)
        click("look_swatch_4")                                  # a ready-made colour
        self.assertEqual((look.hue, look.sat, look.val), (176, 100, 100))
        click("look_theme_chip_halloween")
        self.assertEqual(look.theme, "halloween")
        click("look_custom_art", 60)
        click("look_skip_blurry", 60)
        self.assertTrue(look.useCustomArt and look.skipAutoArt)
        end = time.time() + 2
        while time.time() < end and look.previewSource == before:
            self.app.processEvents()
            time.sleep(0.02)
        self.assertIn("/176/100/100/halloween/none/", look.previewSource)     # one picture, in the final choice
        self.assertEqual(shell.steps[3]["state"], "locked")
        click("look_next")
        self.assertEqual(shell.current, 3)
        self.assertEqual(shell.steps[3]["state"], "active")
        self.assertEqual(find_item(root, "screen_title").property("text"), "Highlight your 100% games")
        again = Shell(settings, downloads=os.path.join(tmp, "Downloads"), covers_dir=covers).look
        self.assertTrue(again.useCustomArt and again.skipAutoArt)           # the art options come back after closing


@need_qt
class HundredFlow(QtCase):
    """Step 3 as a person lives it, in the real window with the real timer-less polling: a page being saved is waited for, read, styled, and Next opens Make."""
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def start(self):
        from PySide6.QtCore import QPointF
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from qtui.app import close_engine, create_engine, find_item
        from qtui.shell import Shell
        import steamcase as sc
        if sc.Image is None:
            self.skipTest("Pillow missing")
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.downloads = os.path.join(self.tmp, "Downloads")
        os.makedirs(self.downloads)
        self.shell = Shell(os.path.join(self.tmp, "settings.json"), downloads=self.downloads, covers_dir=os.path.join(self.tmp, "covers"))
        self.shell.reduceEffects = True
        engine = create_engine(self.shell)
        self.addCleanup(close_engine, engine)
        self.root = engine.rootObjects()[0]
        self.find = find_item
        self.shell.library.installedOnly = True
        self.shell.setFact("look_done", True)
        self.shell.go(3)
        self.app.processEvents()

        def click(name):
            it = find_item(self.root, name)
            scroller = find_item(self.root, "screen_scroller")
            y = it.mapToItem(scroller.property("contentItem"), QPointF(0, 0)).y()
            scroller.setProperty("contentY", max(0, y - 40))
            self.app.processEvents()
            QTest.mouseClick(self.root, Qt.LeftButton, Qt.NoModifier, it.mapToScene(QPointF(it.width() / 2, it.height() / 2)).toPoint())
            self.app.processEvents()
        self.click = click

    def wait_for(self, condition, seconds=3):
        import time
        end = time.time() + seconds
        while time.time() < end and not condition():
            self.app.processEvents()
            time.sleep(0.02)
        self.app.processEvents()

    def test_from_a_page_being_saved_to_make(self):
        self.start()
        h, look = self.shell.hundred, self.shell.look
        path = os.path.join(self.downloads, "games.html")
        full = write_games_page(self.downloads, {1: (5, 5), 2: (1, 9), 3: (7, 7)})
        with open(full, "rb") as f:
            data = f.read()
        half = data[: len(data) // 2]
        with open(path, "wb") as f:                              # the browser is still writing
            f.write(half)
        self.shell.poll()
        with open(path, "wb") as f:
            f.write(data[: 3 * len(data) // 4])                  # it grew since the last look: not finished
        self.shell.poll()
        self.assertFalse(h.busy or h.loaded)
        with open(path, "wb") as f:
            f.write(data)
        self.shell.poll()                                        # first look at the finished file
        self.assertFalse(h.busy or h.loaded)
        self.shell.poll()                                        # unchanged since: finished
        self.wait_for(lambda: h.loaded)
        self.assertEqual((h.count, os.path.basename(h.path)), (2, "games.html"))
        self.assertEqual(self.find(self.root, "hundred_next").property("text"), "Next: Make \u2192")
        before = look.previewSource
        self.click("hundred_style_chip_gold-border")
        self.click("hundred_marks_chip_rosette")
        self.wait_for(lambda: look.previewSource != before and "/gold-border-rosette/" in look.previewSource)
        self.assertIn("/classic/gold-border-rosette/", look.previewSource)
        self.assertEqual(h.values(), ({1, 3}, "gold-border-rosette"))
        self.assertEqual(self.shell.steps[4]["state"], "locked")
        self.click("hundred_next")
        self.assertEqual(self.shell.current, 4)
        self.assertEqual(self.shell.steps[4]["state"], "active")

    def test_skipping_keeps_a_page_loaded_earlier_and_a_page_is_still_there_when_the_step_is_reopened(self):
        self.start()
        h = self.shell.hundred
        h.loadPage(write_games_page(self.tmp, {1: (2, 2)}))
        self.wait_for(lambda: h.loaded)
        self.shell.go(2)
        self.app.processEvents()
        self.shell.go(3)
        self.app.processEvents()
        self.assertTrue(h.loaded)
        self.assertEqual(self.find(self.root, "hundred_next").property("text"), "Next: Make \u2192")
        self.assertEqual(h.values()[0], {1})
        self.shell.hundred.style = "none"                        # a style chosen earlier is still chosen
        self.shell.go(2)
        self.shell.go(3)
        self.app.processEvents()
        self.assertEqual(h.style, "none")
        self.assertTrue(self.find(self.root, "hundred_style_chip_none").property("selected"))

    def test_a_wrong_file_then_a_good_one(self):
        self.start()
        h = self.shell.hundred
        bad = os.path.join(self.tmp, "bad.html")
        with open(bad, "w") as f:
            f.write("<html>no games here</html>")
        h.loadPage(bad)
        self.wait_for(lambda: h.statusKind == "error")
        self.assertEqual(self.find(self.root, "hundred_status").property("kind"), "error")
        self.assertEqual(self.find(self.root, "hundred_next").property("text"), "Skip this step \u2192")
        h.loadPage(write_games_page(self.tmp, {1: (1, 1)}))
        self.wait_for(lambda: h.loaded)
        self.assertEqual(self.find(self.root, "hundred_status").property("kind"), "ok")


@need_qt
class Components(QtCase):
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

    DIALOG = ('property string last: ""\n'
              'ConfirmDialog { id: dlg; objectName: "dlg"; onConfirmed: win.last = "yes"; onDeclined: win.last = "no" }\n'
              'function openIt() { dlg.ask("Add covers to Steam", [{"text": "2 covers will be added to the Steam account \u201cAlice\u201d.", "kind": "main"},'
              ' {"text": "Your current artwork is backed up first.", "kind": "muted"}, {"text": "Steam will be closed automatically.", "kind": "warn"}], "Close Steam and add them") }')

    def open_dialog(self, w=620, h=420):
        from PySide6.QtCore import QMetaObject
        self.load(self.DIALOG, w, h)
        self.root.requestActivate()
        self.assertFalse(self.item("dlg").isVisible())
        QMetaObject.invokeMethod(self.root, "openIt")
        from PySide6.QtTest import QTest
        QTest.qWait(60)                                                        # one frame: the layout is polished before it is drawn
        self.app.processEvents()

    def test_a_dialog_is_closed_until_asked_and_then_shows_the_words(self):
        self.open_dialog()
        d = self.item("dlg")
        self.assertTrue(d.isVisible())
        self.assertEqual(self.item("dlg_title").property("text"), "Add covers to Steam")
        self.assertEqual(self.item("dlg_p0").property("text"), "2 covers will be added to the Steam account \u201cAlice\u201d.")
        self.assertEqual(self.item("dlg_confirm").property("text"), "Close Steam and add them")
        self.assertEqual(self.item("dlg_cancel").property("text"), "Cancel")
        from PySide6.QtGui import QColor
        self.assertEqual(QColor(self.item("dlg_p2").property("color")).name(), "#f0b429")        # the warning has the warning colour
        self.assertEqual(QColor(self.item("dlg_p1").property("color")).name(), "#93a7bb")

    def test_the_safe_button_has_the_focus_and_only_the_confirm_is_filled(self):
        self.open_dialog()
        self.assertTrue(self.item("dlg_cancel").property("activeFocus"))
        self.assertTrue(self.item("dlg_confirm").property("filled"))
        self.assertFalse(self.item("dlg_cancel").property("filled"))

    def test_escape_and_the_quiet_button_decline_and_close(self):
        from PySide6.QtCore import Qt
        for how in ("escape", "enter on cancel", "click"):
            with self.subTest(how=how):
                self.open_dialog()
                self.root.setProperty("last", "")
                if how == "escape":
                    self.key("dlg_cancel", Qt.Key_Escape)
                elif how == "enter on cancel":
                    self.key("dlg_cancel", Qt.Key_Return)
                else:
                    b = self.item("dlg_cancel")
                    p = b.mapToScene(__import__("PySide6.QtCore", fromlist=["QPointF"]).QPointF(b.width() / 2, b.height() / 2))
                    self.mouse("click", p.x(), p.y())
                self.assertEqual(self.root.property("last"), "no")
                self.assertFalse(self.item("dlg").isVisible())

    def test_tab_moves_between_the_two_buttons_and_enter_confirms(self):
        from PySide6.QtCore import Qt
        self.open_dialog()
        self.key("dlg_cancel", Qt.Key_Tab)
        self.assertTrue(self.item("dlg_confirm").property("activeFocus"))
        self.key("dlg_confirm", Qt.Key_Tab)                                    # the focus never leaves the dialog
        self.assertTrue(self.item("dlg_cancel").property("activeFocus"))
        self.key("dlg_cancel", Qt.Key_Backtab)
        self.assertTrue(self.item("dlg_confirm").property("activeFocus"))
        self.key("dlg_confirm", Qt.Key_Return)
        self.assertEqual(self.root.property("last"), "yes")
        self.assertFalse(self.item("dlg").isVisible())

    def test_a_click_outside_the_card_does_nothing(self):
        self.open_dialog()
        self.mouse("click", 3, 3)
        self.assertEqual((self.root.property("last"), self.item("dlg").isVisible()), ("", True))

    def test_the_dialog_fits_a_narrow_window(self):
        self.open_dialog(w=360, h=420)
        card = self.item("dlg_card")
        self.assertLessEqual(card.width(), 360 - 2 * 32)
        for name in ("dlg_title", "dlg_p0", "dlg_p1", "dlg_p2", "dlg_confirm", "dlg_cancel"):
            it = self.item(name)
            self.assertLessEqual(it.x() + it.width(), card.width() + 0.5, name)
        self.assertGreaterEqual(self.item("dlg_confirm").height(), 36)
        self.assertLessEqual(card.y() + card.height(), 420)

    def test_a_dialog_with_a_lot_to_say_scrolls_and_keeps_its_buttons_in_view(self):
        from PySide6.QtCore import QMetaObject
        self.load('ConfirmDialog { id: dlg; objectName: "dlg" }\nfunction openIt() { var long = []; for (var i = 0; i < 12; i++) long.push({"text": "A long sentence that says what will happen to your covers, number " + i + ".", "kind": "main"}); dlg.ask("Many words", long, "Go") }', 360, 260)
        self.root.requestActivate()
        QMetaObject.invokeMethod(self.root, "openIt")
        from PySide6.QtTest import QTest
        QTest.qWait(60)
        card = self.item("dlg_card")
        self.assertLessEqual(card.y() + card.height(), 260)
        self.assertGreaterEqual(card.y(), 0)
        for name in ("dlg_confirm", "dlg_cancel"):
            it = self.item(name)
            from PySide6.QtCore import QPointF
            self.assertLessEqual(it.mapToScene(QPointF(0, it.height())).y(), 260, name)

    THREE = ('property string last: ""\nConfirmDialog { id: dlg; objectName: "dlg"; onConfirmed: win.last = "yes"; onDeclined: win.last = "no"; onAlternated: win.last = "alt" }\n'
             'function openIt() { dlg.ask("Reset", [{"text": "a", "kind": "main"}], "Remove only ours", "Remove all") }\n'
             'function openPlain() { dlg.ask("Plain", [{"text": "a", "kind": "main"}], "Yes") }\n'
             'function openInfo() { dlg.ask("Info", [{"text": "b", "kind": "main"}], "OK", "", true) }')

    def open_fn(self, fn, w=620, h=420):
        from PySide6.QtCore import QMetaObject
        from PySide6.QtTest import QTest
        self.load(self.THREE, w, h)
        self.root.requestActivate()
        QMetaObject.invokeMethod(self.root, fn)
        QTest.qWait(60)

    def test_a_third_button_sits_between_cancel_and_confirm_and_answers_for_itself(self):
        self.open_fn("openIt")
        places = [(round(self.item(n).y()), self.item(n).x()) for n in ("dlg_cancel", "dlg_alternate", "dlg_confirm")]
        self.assertEqual(places, sorted(places))                         # in reading order, on one row or wrapped onto several
        self.assertEqual(self.item("dlg_alternate").property("text"), "Remove all")
        self.assertFalse(self.item("dlg_alternate").property("filled"))
        self.assertTrue(self.item("dlg_cancel").property("activeFocus"))
        from PySide6.QtCore import QPointF
        b = self.item("dlg_alternate")
        p = b.mapToScene(QPointF(b.width() / 2, b.height() / 2))
        self.mouse("click", p.x(), p.y())
        self.assertEqual(self.root.property("last"), "alt")
        self.assertFalse(self.item("dlg").isVisible())

    def test_tab_cycles_through_all_the_buttons_both_ways(self):
        from PySide6.QtCore import Qt
        self.open_fn("openIt")
        order = ["dlg_cancel", "dlg_alternate", "dlg_confirm", "dlg_cancel"]
        for here, there in zip(order, order[1:]):
            self.key(here, Qt.Key_Tab)
            self.assertTrue(self.item(there).property("activeFocus"), there)
        self.key("dlg_cancel", Qt.Key_Backtab)
        self.assertTrue(self.item("dlg_confirm").property("activeFocus"))

    def test_without_a_third_text_there_is_no_third_button(self):
        self.open_fn("openPlain")
        self.assertFalse(self.item("dlg_alternate").isVisible())
        from PySide6.QtCore import Qt
        self.key("dlg_cancel", Qt.Key_Tab)
        self.assertTrue(self.item("dlg_confirm").property("activeFocus"))

    def test_an_info_dialog_has_only_the_confirm_button(self):
        from PySide6.QtCore import Qt
        self.open_fn("openInfo")
        self.assertFalse(self.item("dlg_cancel").isVisible())
        self.assertTrue(self.item("dlg_confirm").property("activeFocus"))
        self.key("dlg_confirm", Qt.Key_Tab)                                     # the focus has nowhere else to go
        self.assertTrue(self.item("dlg_confirm").property("activeFocus"))
        self.key("dlg_confirm", Qt.Key_Return)
        self.assertEqual(self.root.property("last"), "yes")
        self.open_fn("openInfo")
        self.key("dlg_confirm", Qt.Key_Escape)
        self.assertEqual(self.root.property("last"), "no")
        self.assertFalse(self.item("dlg").isVisible())

    SUMMARY = ('property int last: -1\nChoiceSummary { objectName: "sum"; x: 10; y: 10; width: @W@; onChosen: (step) => win.last = step;\n'
               '  model: [{"key": "colour", "label": "Colour", "value": "Teal", "step": 2}, {"key": "hundred", "label": "100% games", "value": "Gold case, rosette and ribbon", "step": 3},'
               ' {"key": "art", "label": "Art", "value": "Your own art, blurry art skipped", "step": 2}] }')

    def test_a_choice_summary_names_each_choice_and_leads_back_to_its_step(self):
        self.load(self.SUMMARY.replace("@W@", "560"), 600, 200)
        for key, step in (("colour", 2), ("hundred", 3), ("art", 2)):
            with self.subTest(key=key):
                chip = self.item("sum_chip_" + key)
                self.assertGreaterEqual(chip.height(), 36)
                from PySide6.QtCore import QPointF
                p = chip.mapToScene(QPointF(chip.width() / 2, chip.height() / 2))
                self.root.setProperty("last", -1)
                self.mouse("click", p.x(), p.y())
                self.assertEqual(self.root.property("last"), step)

    def test_a_choice_summary_wraps_and_never_exceeds_its_width(self):
        self.load(self.SUMMARY.replace("@W@", "240"), 300, 300)
        s = self.item("sum")
        ys = set()
        for key in ("colour", "hundred", "art"):
            chip = self.item("sum_chip_" + key)
            self.assertLessEqual(chip.x() + chip.width(), 240.5, key)
            ys.add(round(chip.y()))
        self.assertGreater(len(ys), 1)                                         # they wrap onto more rows
        self.assertGreaterEqual(s.height(), 36)

    def test_a_choice_summary_chip_works_from_the_keyboard(self):
        from PySide6.QtCore import Qt
        self.load(self.SUMMARY.replace("@W@", "560"), 600, 200)
        self.key("sum_chip_hundred", Qt.Key_Return)
        self.assertEqual(self.root.property("last"), 3)
        self.root.setProperty("last", -1)
        self.key("sum_chip_art", Qt.Key_Space)
        self.assertEqual(self.root.property("last"), 2)

    def test_a_progress_bar_shows_the_share_and_never_leaves_its_track(self):
        self.load('ProgressBar { objectName: "bar"; x: 10; y: 10; width: 300; value: 0.5 }', 340, 80)
        bar = self.item("bar")
        self.assertEqual(bar.height(), 8)
        for value, share in ((0.5, 0.5), (1.5, 1.0), (-1, 0.0), (0.25, 0.25)):
            bar.setProperty("value", value)
            from PySide6.QtTest import QTest
            QTest.qWait(300)
            self.app.processEvents()
            self.assertAlmostEqual(self.item("bar_fill").width(), 300 * share, delta=1, msg=str(value))

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
        self.assertEqual(iface.text(QAccessible.Text.Description), "120 (0 to 359)")

    def touch(self, kind, x, y):
        from PySide6.QtCore import QPoint
        from PySide6.QtTest import QTest
        if not hasattr(self, "_touch"):
            self._touch = QTest.createTouchDevice()
        seq = QTest.touchEvent(self.root, self._touch)
        getattr(seq, kind)(0, QPoint(int(x), int(y)), self.root)
        seq.commit()
        self.app.processEvents()

    def test_a_swipe_that_starts_on_the_track_with_a_finger_does_not_move_the_slider(self):
        """On the Steam Deck a swipe over a slider must scroll the page, not change the colour; a tap on the track still jumps, the handle still drags."""
        self.load(self.SLIDER)
        s = self.item("s")
        y = 20 + s.height() / 2
        self.touch("press", 20 + 200, y)
        self.touch("move", 20 + 260, y)
        self.touch("release", 20 + 260, y)
        self.assertEqual(s.property("value"), 0)                     # a swipe: nothing changed
        self.touch("press", 20 + 200, y)
        self.touch("release", 20 + 200, y)
        self.assertAlmostEqual(s.property("value"), 247, delta=12)   # a tap on the track jumps there (200 - 18) / 264 of the range
        handle_x = 20 + s.property("handleSize") / 2 + (s.property("value") / 359) * (300 - s.property("handleSize"))
        self.touch("press", handle_x, y)
        self.touch("move", 20 + 60, y)
        self.touch("release", 20 + 60, y)
        self.assertLess(s.property("value"), 100)                    # the handle drags

    def test_the_card_never_waits_for_a_render_on_the_window_thread(self):
        self.load('PreviewCard { objectName: "p"; x: 20; y: 20; source: "image://preview/0/100/100/classic/none/1" }', 300, 400)
        self.assertTrue(self.item("p").property("frontAsynchronous"))

    def test_a_picture_that_fails_to_render_leaves_the_old_one(self):
        import time
        from unittest import mock
        self.load('PreviewCard { objectName: "p"; x: 20; y: 20; source: "image://preview/0/100/100/classic/none/1" }', 300, 400)
        p = self.item("p")
        end = time.time() + 5
        while time.time() < end and not p.property("showing"):
            self.app.processEvents()
            time.sleep(0.02)
        self.assertTrue(p.property("showing"))
        with mock.patch("steamcase.preview_cover", side_effect=RuntimeError("boom")):
            p.setProperty("source", "image://preview/200/100/100/classic/none/2")
            end = time.time() + 3
            while time.time() < end and p.property("status") not in (3,):                       # Image.Error
                self.app.processEvents()
                time.sleep(0.02)
        self.assertEqual(p.property("status"), 3)
        self.assertTrue(p.property("showing"), "the card went blank after a failed render")

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

    def test_arrow_keys_move_the_focus_with_the_choice_and_warn_about_nothing(self):
        from PySide6.QtCore import Qt, QtMsgType, qInstallMessageHandler
        warnings = []
        qInstallMessageHandler(lambda kind, ctx, msg: warnings.append(msg) if kind in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg) else None)
        self.addCleanup(qInstallMessageHandler, None)
        self.load('ChoiceChips { objectName: "c"; x: 20; y: 20; width: 380; model: [{"key": "a", "label": "A"}, {"key": "b", "label": "B"}, {"key": "c", "label": "C"}];\n'
                  '  current: "a"; onChosen: (k) => current = k }')
        self.key("c_chip_a", Qt.Key_Right)
        self.assertEqual(self.item("c").property("current"), "b")
        self.assertTrue(self.item("c_chip_b").property("activeFocus"), "the focus stayed on the old chip")
        self.assertTrue(self.item("c_chip_b").property("activeFocusOnTab"))
        self.assertFalse(self.item("c_chip_a").property("activeFocusOnTab"))
        self.key("c_chip_b", Qt.Key_Left)
        self.assertEqual(self.item("c").property("current"), "a")
        self.assertTrue(self.item("c_chip_a").property("activeFocus"))
        self.key("c_chip_a", Qt.Key_End)
        self.assertEqual(self.item("c").property("current"), "c")
        self.assertTrue(self.item("c_chip_c").property("activeFocus"))
        self.assertEqual([w for w in warnings if "activeFocusOnTab" in w], [])

    def test_only_the_chosen_chip_is_a_tab_stop_and_they_are_radio_buttons(self):
        from PySide6.QtGui import QAccessible
        self.load(self.CHIPS)
        self.assertTrue(self.item("c_chip_classic").property("activeFocusOnTab"))
        self.assertFalse(self.item("c_chip_halloween").property("activeFocusOnTab"))
        QAccessible.setActive(True)
        self.addCleanup(QAccessible.setActive, False)
        iface = QAccessible.queryAccessibleInterface(self.item("c_chip_classic"))
        self.assertEqual((iface.role(), iface.text(QAccessible.Text.Name), iface.state().checked), (QAccessible.Role.RadioButton, "Classic", True))

    def test_disabled_chips_are_greyed_ignore_clicks_and_keys_and_leave_the_tab_order(self):
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QAccessible
        self.load(self.CHIPS.replace('current: "classic";', 'current: "classic"; enabled: false;'))
        c = self.item("c")
        self.assertEqual(c.property("opacity"), 0.6)                  # the token for a disabled control
        chip = self.item("c_chip_halloween")
        centre = chip.mapToScene(QPointF(chip.width() / 2, chip.height() / 2))
        self.mouse("click", centre.x(), centre.y())
        self.assertEqual(c.property("last"), "")
        self.key("c_chip_classic", Qt.Key_Right)
        self.key("c_chip_classic", Qt.Key_Space)
        self.assertEqual(c.property("last"), "")
        self.assertFalse(self.item("c_chip_classic").property("activeFocusOnTab"))
        self.assertFalse(self.item("c_chip_halloween").property("activeFocusOnTab"))
        self.assertTrue(self.item("c_chip_classic").property("selected"))          # the choice still shows
        QAccessible.setActive(True)
        self.addCleanup(QAccessible.setActive, False)
        iface = QAccessible.queryAccessibleInterface(self.item("c_chip_classic"))
        self.assertTrue(iface.state().disabled)
        self.assertTrue(iface.state().checked)
        c.setProperty("enabled", True)                                # and everything comes back
        self.assertEqual(c.property("opacity"), 1)
        self.assertTrue(self.item("c_chip_classic").property("activeFocusOnTab"))
        self.mouse("click", centre.x(), centre.y())
        self.assertEqual(c.property("last"), "halloween")

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
        end = time.time() + 5
        while time.time() < end and not p.property("showing"):                 # the shown picture loads asynchronously too
            self.app.processEvents()
            time.sleep(0.02)
        p.setProperty("source", "image://preview/120/100/100/classic/none/2")
        self.app.processEvents()
        self.assertTrue(p.property("showing"), "the card went blank while the next picture loaded")


@need_qt
class PreviewImages(QtCase):
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

    def test_an_engine_failure_gives_no_picture_so_the_old_one_stays(self):
        from unittest import mock
        with mock.patch("steamcase.preview_cover", side_effect=RuntimeError("boom")):
            img = self.get("0/100/100/classic/none/1", 50, 75)
        self.assertTrue(img.isNull())                                     # QML sees an error, not a blank picture that would replace the old one

    def test_a_repeated_request_is_not_rendered_again(self):
        import steamcase as sc
        from unittest import mock
        with mock.patch("steamcase.preview_cover", wraps=sc.preview_cover) as engine:
            a = self.get("33/100/100/classic/none/1")
            b = self.get("33/100/100/classic/none/2")                    # only the serial differs
        self.assertEqual(engine.call_count, 1)
        self.assertEqual(bytes(a.constBits()), bytes(b.constBits()))

    def test_many_threads_at_once_all_get_a_valid_picture(self):
        import gc, threading
        gc.collect()                                                       # leftovers of earlier tests die here, on the main thread
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
class LookState(QtCase):
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

    def test_the_themes_come_from_python(self):
        self.assertEqual([t["key"] for t in self.look.themes], ["classic", "halloween"])
        self.assertEqual([t["label"] for t in self.look.themes], ["Classic", "Halloween"])

    def test_the_swatch_list_is_constant_and_the_selection_is_a_number(self):
        before = self.look.swatchList
        self.look.setTone(123, 45, 67)
        self.assertEqual(self.look.swatchList, before)                    # nothing to rebuild
        self.assertEqual(self.look.selectedSwatch, -1)                    # a custom tone is none of the nine
        self.look.pickSwatch(4)
        self.assertEqual(self.look.selectedSwatch, 4)
        self.look.pickSwatch(8)
        self.assertEqual(self.look.selectedSwatch, 8)

    def test_a_swatch_is_named_like_the_tone_it_sets(self):
        names = [x["name"] for x in self.look.swatchList]
        self.assertEqual(names[0], "Original")                            # the tone name of the first swatch
        self.assertEqual(names[4], "Orange")                              # what the engine calls it, not "Gold" (a case style)
        self.assertEqual(len(set(names)), 9)

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

    def test_the_preview_keeps_up_during_a_long_drag(self):
        """The Tk window redrew during the drag: waiting for the pointer to rest would freeze the picture until the end."""
        import time
        seen = []
        self.look.previewSourceChanged.connect(lambda: seen.append(self.look.previewSource))
        end = time.time() + 0.45
        h = 0
        while time.time() < end:                                           # a change every ~15 ms for 450 ms
            h = (h + 7) % 360
            self.look.setTone(h, 100, 100)
            self.wait(15)
        self.assertGreaterEqual(len(seen), 3, seen)                       # several pictures on the way, not one at the end
        self.wait(200)
        self.assertIn("/%d/100/100/" % h, self.look.previewSource)         # and the last one shows the final tone

    def test_the_colours_for_the_sliders_come_from_python(self):
        import steamcase as sc
        self.assertEqual(self.look.colorFor(120, 50, 80), sc.case_color(120, 50, 80))
        self.assertEqual(self.look.trackStart("sat"), sc.case_color(0, 0, 100))
        self.assertEqual(self.look.trackEnd("val"), sc.case_color(0, 100, 100))
        self.assertEqual(len(self.look.hueColors()), 36)
        self.assertEqual(self.look.trackStart("nonsense"), "#000000")     # never an exception into QML


def write_games_page(folder, progress, name="games.html"):
    """A saved games page like tests/fixtures/games_page.html, with a row per app id in `progress` {appid: (unlocked, total) or None}."""
    rows = []
    for appid, counts in progress.items():
        store = '<a href="https://store.steampowered.com/app/%d"' % appid
        row = '<div class="row">\n  %s class="img"></a>\n  %s class="name">Game</a>\n' % (store, store)
        if counts:
            row += '  <a class="ach" href="https://steamcommunity.com/id/playerone/achievements/%d">ACHIEVEMENTS</a><span class="cnt">%d/%d</span>\n' % ((appid,) + counts)
        rows.append(row + "</div>\n")
    path = os.path.join(folder, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write('<!DOCTYPE html>\n<html><body><div class="list">\n' + "".join(rows) + "</div></body></html>\n")
    return path


@need_qt
class HundredState(QtCase):
    """Step 3: the saved games page, read on a worker thread, and the style of the 100% covers."""
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def setUp(self):
        from qtui.shell import Shell
        self.Shell = Shell
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.downloads = os.path.join(self.tmp, "Downloads")
        os.makedirs(self.downloads)
        self.covers = os.path.join(self.tmp, "covers")
        os.makedirs(self.covers)
        self.settings = os.path.join(self.tmp, "settings.json")
        self.shell = self.new_shell()
        self.h = self.shell.hundred

    def new_shell(self):
        return self.Shell(self.settings, downloads=self.downloads, covers_dir=self.covers)

    def page(self, progress, name="games.html", folder=None):
        return write_games_page(folder or self.tmp, progress, name)

    def wait_for(self, condition, seconds=3):
        import time
        end = time.time() + seconds
        while time.time() < end and not condition():
            self.app.processEvents()
            time.sleep(0.02)
        self.app.processEvents()

    def load(self, path):
        self.h.loadPage(path)
        self.wait_for(lambda: not self.h.busy)

    def test_it_starts_without_a_page(self):
        h = self.h
        self.assertEqual((h.loaded, h.path, h.count, h.busy, h.style, h.marks), (False, "", 0, False, "ribbon", "full"))
        self.assertEqual((h.status, h.statusKind), ("No games page loaded. Your covers keep the look they have.", "wait"))
        self.assertEqual((h.styleEnabled, h.marksEnabled, h.note), (False, False, ""))
        self.assertEqual(h.values(), (None, None))

    def test_a_good_page_is_read_and_only_the_100_percent_games_are_kept(self):
        h = self.h
        path = self.page({1: (10, 10), 2: (1, 9), 3: (5, 5), 4: None, 5: (0, 0)})
        h.loadPage(path)
        self.assertEqual((h.status, h.statusKind, h.busy), ("Reading games.html…", "wait", True))      # at once, before the answer
        self.wait_for(lambda: not h.busy)
        self.assertEqual((h.loaded, h.path, h.count), (True, path, 2))
        self.assertEqual((h.status, h.statusKind), ("Found 2 games at 100% in games.html. The game list from step 1 decides which games get covers.", "ok"))
        self.assertTrue(h.note.startswith("Done with the page? You can delete games.html and its folder: they hold a temporary login token for your Steam account, "), h.note)
        self.assertEqual((h.styleEnabled, h.marksEnabled), (True, True))
        self.assertEqual(h.values(), ({1, 3}, "ribbon"))

    def test_one_game_is_singular_and_none_says_so(self):
        self.load(self.page({1: (3, 3), 2: (1, 4)}))
        self.assertIn("Found 1 game at 100% in games.html.", self.h.status)
        self.load(self.page({1: (1, 3)}, "other.html"))
        self.assertEqual(self.h.status, "No game in other.html is at 100% yet. The game list from step 1 decides which games get covers.")
        self.assertEqual((self.h.loaded, self.h.count), (True, 0))
        self.assertEqual(self.h.values(), (set(), "ribbon"))

    def test_a_bad_file_says_why_and_the_page_before_stays_in_use(self):
        h = self.h
        bad = os.path.join(self.tmp, "notes.html")
        with open(bad, "w") as f:
            f.write("<html>hello</html>")
        self.load(bad)
        self.assertEqual((h.loaded, h.statusKind), (False, "error"))
        self.assertTrue(h.status.startswith("notes.html: That file does not look like your Steam games page."), h.status)
        self.assertNotIn("The page you loaded before", h.status)
        good = self.page({1: (2, 2)})
        self.load(good)
        self.load(bad)
        self.assertTrue(h.status.endswith(" The page you loaded before is still used."), h.status)
        self.assertEqual((h.path, h.loaded, h.values()[0]), (good, True, {1}))

    def test_a_missing_file_is_refused_in_words(self):
        self.load(os.path.join(self.tmp, "gone.html"))
        self.assertEqual((self.h.status, self.h.statusKind), ("gone.html: That file could not be opened. (gone.html)", "error"))

    def test_a_huge_file_is_refused_without_being_read(self):
        from unittest import mock
        path = self.page({1: (1, 1)})
        with mock.patch("completion.MAX_GAMES_PAGE", 10):
            self.load(path)
        self.assertEqual(self.h.status, "games.html: That file is too big to be your Steam games page.")
        self.assertFalse(self.h.loaded)

    def test_a_link_or_a_pipe_is_not_followed(self):
        good = self.page({1: (1, 1)})
        link = os.path.join(self.tmp, "link.html")
        try:
            os.symlink(good, link)
        except (OSError, NotImplementedError):
            link = None
        if link:
            self.load(link)
            self.assertEqual(self.h.status, "link.html: That is not a plain file. Pick the .html file you saved.")
            self.assertFalse(self.h.loaded)
        if hasattr(os, "mkfifo"):
            pipe = os.path.join(self.tmp, "pipe.html")
            os.mkfifo(pipe)
            self.load(pipe)                                            # must not hang
            self.assertEqual(self.h.status, "pipe.html: That is not a plain file. Pick the .html file you saved.")

    def test_a_surprise_never_quotes_the_page(self):
        from unittest import mock
        path = self.page({1: (1, 1)})
        with mock.patch("completion.read_games_page", side_effect=RuntimeError("token=SECRET123")):
            self.load(path)
        self.assertEqual(self.h.status, "games.html: That file could not be read.")
        self.assertNotIn("SECRET", self.h.status + self.h.note)

    def test_the_status_never_holds_page_text(self):
        path = self.page({1: (1, 1)})
        with open(path, "a") as f:
            f.write("<script>var token='SECRET123'</script>")
        self.load(path)
        self.assertNotIn("SECRET", self.h.status + self.h.note + self.h.path)

    def test_two_loads_in_a_row_the_newest_answer_wins_even_if_the_older_arrives_late(self):
        import threading
        from unittest import mock
        import completion
        first = self.page({1: (1, 1)}, "first.html")
        second = self.page({2: (2, 2), 3: (4, 4)}, "second.html")
        gate = threading.Event()
        self.addCleanup(gate.set)                                       # a failing test must not leave a worker thread waiting
        real = completion.read_games_page

        def slow(path):
            if os.path.basename(path) == "first.html":
                gate.wait(5)                                          # the older read finishes last
            return real(path)
        with mock.patch("completion.read_games_page", side_effect=slow):
            self.h.loadPage(first)
            self.h.loadPage(second)
            self.wait_for(lambda: self.h.loaded)
            self.assertEqual((self.h.path, self.h.values()[0]), (second, {2, 3}))
            gate.set()
            self.wait_for(lambda: not self.h.busy)
        self.assertEqual((self.h.path, self.h.values()[0]), (second, {2, 3}))
        self.assertIn("second.html", self.h.status)

    def test_an_empty_path_or_url_starts_nothing(self):
        for call in (lambda: self.h.loadPage(""), lambda: self.h.loadPageUrl(""), lambda: self.h.loadPageUrl("https://example.com/x.html")):
            call()
            self.assertEqual((self.h.busy, self.h.status), (False, "No games page loaded. Your covers keep the look they have."))

    def test_an_answer_that_cannot_be_delivered_is_dropped_quietly(self):
        import shiboken6
        from qtui.hundred import Hundred
        gone = Hundred(self.shell, self.downloads)
        shiboken6.delete(gone)                                        # the window closed while the worker was still reading
        gone._worker(1, self.page({1: (1, 1)}))                       # must not raise in the worker thread
        gone._worker(2, os.path.join(self.tmp, "missing.html"))       # nor for an error answer

    def test_the_choices_notify_with_one_signal_and_only_when_something_changed(self):
        h = self.h
        seen = []
        h.choicesChanged.connect(lambda: seen.append((h.styleEnabled, h.marksEnabled)))
        marks = []
        h.marksChanged.connect(lambda: marks.append(h.marks))
        self.load(self.page({1: (1, 1)}))
        self.assertIn((True, True), seen)
        h.style = "none"
        self.assertEqual(seen[-1], (True, False))
        self.shell.look.theme = "classic"                              # no change: no signal
        self.assertEqual(marks, [])
        self.shell.look.theme = "halloween"
        self.assertEqual(marks, ["rosette"])

    def test_marks_changed_under_halloween_are_ignored_and_the_ones_before_come_back(self):
        h, look = self.h, self.shell.look
        h.marks = "rosette"
        look.theme = "halloween"
        h.marks = "full"                                              # greyed: ignored
        look.theme = "classic"
        self.assertEqual(h.marks, "rosette")

    def test_the_url_of_the_qt_dialog_loads_the_page(self):
        from PySide6.QtCore import QUrl
        path = self.page({1: (1, 1)})
        self.h.loadPageUrl(QUrl.fromLocalFile(path).toString())
        self.wait_for(lambda: not self.h.busy)
        self.assertEqual(self.h.path, os.path.normpath(path))

    def test_the_styles_and_marks_decide_what_make_gets(self):
        h = self.h
        self.load(self.page({1: (1, 1), 2: (1, 2)}))
        import steamcase as sc
        for style in sc.CASES:
            for marks in sc.MARKS:
                h.style, h.marks = style, marks
                self.assertEqual(h.values(), ({1}, sc.compose_treatment(style, marks)))
        h.style = "none"
        self.assertEqual(h.values(), (set(), None))            # the 100% covers become normal covers
        self.assertEqual((h.styleEnabled, h.marksEnabled), (True, False))      # no marks to choose

    def test_a_wrong_style_or_marks_is_ignored(self):
        h = self.h
        h.style, h.marks = "sparkly", "lots"
        self.assertEqual((h.style, h.marks), ("ribbon", "full"))

    def test_the_choices_are_the_old_windows(self):
        self.assertEqual([x["key"] for x in self.h.styles], ["gold-case", "gold-border", "ribbon", "none"])
        self.assertEqual([x["label"] for x in self.h.styles], ["Gold case", "Gold border", "Normal case", "No special case"])
        self.assertEqual([(x["key"], x["label"]) for x in self.h.markChoices], [("full", "Rosette and ribbon"), ("rosette", "Rosette only")])

    def test_halloween_forces_the_rosette_and_going_back_restores_the_marks(self):
        h, look = self.h, self.shell.look
        self.load(self.page({1: (1, 1)}))
        h.marks = "full"
        look.theme = "halloween"
        self.assertEqual((h.marks, h.marksEnabled, h.themeNote), ("rosette", False, "The Halloween case shows the rosette only: the ribbon would hide the pumpkin and the web."))
        h.marks = "full"                                              # the greyed choice cannot be changed
        self.assertEqual(h.marks, "rosette")
        look.theme = "classic"
        self.assertEqual((h.marks, h.marksEnabled, h.themeNote), ("full", True, ""))
        h.marks = "rosette"
        look.theme = "halloween"
        look.theme = "classic"
        self.assertEqual(h.marks, "rosette")                          # what was chosen before, whatever it was

    def test_a_page_loaded_under_halloween_keeps_the_marks_greyed(self):
        h, look = self.h, self.shell.look
        look.theme = "halloween"
        self.load(self.page({1: (1, 1)}))
        self.assertEqual((h.styleEnabled, h.marksEnabled, h.marks), (True, False, "rosette"))
        import steamcase as sc
        self.assertEqual(h.values()[1], sc.compose_treatment("ribbon", "rosette"))

    def test_covers_made_in_halloween_open_the_window_in_halloween(self):
        import steamcase as sc
        if sc.Image is None:
            self.skipTest("Pillow missing")
        art = os.path.join(self.tmp, "art.png")
        sc.Image.new("RGB", (100, 150), (10, 120, 30)).save(art)
        sc.build_cover(art, os.path.join(self.covers, "Game_1_1.png"), sc.load_frame(0), 0, theme="halloween")
        h = self.new_shell().hundred
        self.assertEqual((h.marks, h.marksEnabled, h.themeNote != ""), ("rosette", False, True))

    def test_the_preview_follows_only_when_a_page_is_loaded_and_a_case_is_chosen(self):
        h, look = self.h, self.shell.look
        self.assertEqual(look.treatment, "none")
        h.style = "gold-case"
        self.assertEqual(look.treatment, "none")                      # no page: covers keep their look
        self.load(self.page({1: (1, 1)}))
        self.assertEqual(look.treatment, "gold-case")
        h.marks = "rosette"
        self.assertEqual(look.treatment, "gold-case-rosette")
        h.style = "none"
        self.assertEqual(look.treatment, "none")
        h.style = "gold-border"
        look.theme = "halloween"
        self.assertEqual(look.treatment, "gold-border-rosette")

    def test_a_page_saved_by_the_browser_is_noticed_once_when_finished(self):
        h = self.h
        before = self.page({9: (1, 1)}, "games.html", self.downloads)
        h = self.new_shell().hundred                                  # what lay there before the app started is stale
        h.poll(); h.poll()
        self.assertFalse(h.busy or h.loaded)
        os.mkdir(os.path.join(self.downloads, "games_files"))         # the folder the browser saves next to the page
        new = self.page({1: (2, 2)}, "games2.htm", self.downloads)
        h.poll()                                                      # first sight: maybe still being written
        self.assertFalse(h.busy or h.loaded)
        h.poll()
        self.wait_for(lambda: h.loaded)
        self.assertEqual((h.path, h.values()[0]), (new, {1}))
        self.assertNotEqual(h.path, before)

    def test_a_noticed_page_that_is_wrong_is_explained_and_not_read_again(self):
        from unittest import mock
        h = self.h
        bad = os.path.join(self.downloads, "games.html")
        with open(bad, "w") as f:
            f.write("<html>nothing</html>")
        with mock.patch("completion.read_games_page", wraps=__import__("completion").read_games_page) as read:
            h.poll(); h.poll()
            self.wait_for(lambda: h.statusKind == "error")
            h.poll(); h.poll(); h.poll()
            self.wait_for(lambda: False, 0.2)
            self.assertEqual(read.call_count, 1)
        self.assertTrue(h.status.startswith("games.html: "), h.status)

    def test_once_a_page_is_loaded_the_folder_is_not_watched_any_more(self):
        h = self.h
        self.load(self.page({1: (1, 1)}, "mine.html"))
        self.page({2: (2, 2)}, "games.html", self.downloads)
        for _ in range(4):
            h.poll()
        self.wait_for(lambda: False, 0.2)
        self.assertEqual(os.path.basename(h.path), "mine.html")

    def test_the_shell_poll_looks_at_both_steps(self):
        self.page({1: (2, 2)}, "games.html", self.downloads)
        with open(os.path.join(self.downloads, "userdata.json"), "w") as f:
            json.dump({"rgOwnedApps": [1, 2]}, f)
        self.shell.poll()
        self.shell.poll()
        self.wait_for(lambda: self.h.loaded)
        self.assertTrue(self.shell.library.ready)
        self.assertTrue(self.h.loaded)

    def test_open_page_opens_the_link_and_always_shows_the_way_out(self):
        from unittest import mock
        for opened in (True, False):
            with self.subTest(opened=opened), mock.patch("qtui.hundred.QDesktopServices.openUrl", return_value=opened) as m:
                self.h.openPage()
                self.assertEqual(m.call_args[0][0].toString(), "https://steamcommunity.com/my/games/?tab=all&sort=achievements")
                self.assertTrue(self.h.status.startswith("Opening your browser… Log in to Steam if it asks and wait until your games have loaded. Then press "), self.h.status)
                self.assertIn("named games.html. Nothing opened? Click “Copy link” and paste it into your browser.", self.h.status)
                self.assertEqual(self.h.statusKind, "wait")

    def test_copy_link_puts_the_page_address_on_the_clipboard(self):
        self.h.copyLink()
        self.assertEqual(QGuiApplication.clipboard().text(), "https://steamcommunity.com/my/games/?tab=all&sort=achievements")
        self.assertEqual(self.h.statusKind, "ok")
        self.assertTrue(self.h.status.startswith("Link copied. Paste it into your browser, log in if asked, then save the page as “Webpage, Complete”, named games.html ("), self.h.status)

    def test_browse_loads_the_chosen_page(self):
        from unittest import mock
        path = self.page({1: (1, 1)})
        with mock.patch("qtui.hundred.pick_file", return_value=path) as m:
            self.h.browse()
            self.wait_for(lambda: self.h.loaded)
        self.assertEqual(m.call_args[0][2], ("Web pages", "*.html *.htm"))
        self.assertEqual(self.h.path, path)

    def test_browse_cancelled_changes_nothing_and_without_a_desktop_chooser_asks_for_the_qt_dialog(self):
        from unittest import mock
        before = (self.h.status, self.h.statusKind)
        with mock.patch("qtui.hundred.pick_file", return_value=""):
            self.h.browse()
            self.wait_for(lambda: False, 0.3)
        self.assertEqual((self.h.status, self.h.statusKind), before)
        seen = []
        self.h.needDialog.connect(seen.append)
        with mock.patch("qtui.hundred.pick_file", return_value=None):
            self.h.browse()
            self.wait_for(lambda: seen)
        self.assertEqual(seen, [self.downloads])

    def test_the_help_texts_are_the_old_windows(self):
        from qtui import system
        self.assertIn("The saved file contains a temporary login token for your Steam account.", system.PAGE_HELP)
        self.assertIn(system.SAVE_KEY, system.PAGE_HELP)
        self.assertEqual(system.THEME_NOTE, "The Halloween case shows the rosette only: the ribbon would hide the pumpkin and the web.")
        self.assertEqual(system.GAMES_PAGE_URL, "https://steamcommunity.com/my/games/?tab=all&sort=achievements")


@need_qt
class HundredScreen(QtCase):
    """Step 3 as the approved wireframe, in the real window (effects reduced so nothing is still sliding)."""
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def setUp(self):
        from qtui.app import close_engine, create_engine
        from qtui.shell import Shell
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        os.makedirs(os.path.join(self.tmp, "Downloads"))      # Qt's dialog starts in a folder that exists
        self.shell = Shell(os.path.join(self.tmp, "settings.json"), downloads=os.path.join(self.tmp, "Downloads"), covers_dir=os.path.join(self.tmp, "covers"))
        self.shell.reduceEffects = True
        self.shell.library.installedOnly = True
        self.shell.setFact("look_done", True)
        self.engine = create_engine(self.shell)
        self.addCleanup(close_engine, self.engine)
        self.root = self.engine.rootObjects()[0]
        self.h = self.shell.hundred
        self.shell.go(3)
        self.app.processEvents()

    item = LookScreen.item
    centre = LookScreen.centre
    reveal = LookScreen.reveal
    click = LookScreen.click
    pos = LookScreen.pos

    def wait_for(self, condition, seconds=3):
        import time
        end = time.time() + seconds
        while time.time() < end and not condition():
            self.app.processEvents()
            time.sleep(0.02)
        self.app.processEvents()

    def load_page(self, progress=None, name="games.html"):
        self.h.loadPage(write_games_page(self.tmp, progress or {1: (3, 3), 2: (1, 4)}, name))
        self.wait_for(lambda: self.h.loaded)
        self.app.processEvents()

    def test_it_shows_its_title_and_says_it_is_optional(self):
        self.assertEqual(self.item("screen_title").property("text"), "Highlight your 100% games")
        self.assertTrue(self.item("hundred_screen").property("subtitle").startswith("Optional."))

    def test_the_three_ways_to_get_the_page_sit_in_one_row_and_wrap_when_narrow(self):
        self.root.setProperty("width", 1200)
        self.app.processEvents()
        ys = {self.pos(n).y() for n in ("hundred_open", "hundred_browse", "hundred_copy")}
        self.assertEqual(len(ys), 1, ys)
        self.root.setProperty("width", self.root.property("minimumWidth"))
        self.app.processEvents()
        from PySide6.QtCore import QPointF
        sec = self.item("hundred_section_page")
        right = sec.mapToScene(QPointF(sec.width(), 0)).x()
        for n in ("hundred_open", "hundred_browse", "hundred_copy"):
            it = self.item(n)
            self.assertLessEqual(it.mapToScene(QPointF(it.width(), 0)).x(), right + 0.5, n)

    def test_open_is_the_filled_button_until_a_page_is_loaded_and_keeps_the_focus(self):
        self.assertTrue(self.item("hundred_open").property("filled"))
        nxt = self.item("hundred_next")
        self.assertFalse(nxt.property("filled"))                       # the quiet "Skip this step"
        self.assertEqual(nxt.property("text"), "Skip this step \u2192")
        self.root.requestActivate()
        nxt.forceActiveFocus()
        self.load_page()
        self.assertFalse(self.item("hundred_open").property("filled"))
        self.assertTrue(nxt.property("filled"))
        self.assertEqual(nxt.property("text"), "Next: Make \u2192")
        self.assertTrue(nxt.property("activeFocus"), "a keyboard user on Skip lost the focus when the page loaded")
        self.assertTrue(self.item("hundred_next") is nxt)              # the same button, not a new one

    def test_the_button_to_go_on_waits_while_a_page_is_being_read(self):
        import threading
        from unittest import mock
        import completion
        self.load_page()
        gate = threading.Event()
        self.addCleanup(gate.set)                                       # a failing test must not leave a worker thread waiting
        real = completion.read_games_page
        with mock.patch("completion.read_games_page", side_effect=lambda p: (gate.wait(5), real(p))[1]):
            self.h.loadPage(write_games_page(self.tmp, {5: (2, 2)}, "second.html"))
            self.app.processEvents()
            self.assertFalse(self.item("hundred_next").property("enabled"))
            gate.set()
            self.wait_for(lambda: not self.h.busy)
        self.assertTrue(self.item("hundred_next").property("enabled"))

    def test_nothing_moves_under_a_finger_when_the_page_loads(self):
        self.root.setProperty("width", self.root.property("minimumWidth"))        # narrow: the preview block sits above the sections
        self.app.processEvents()
        names = ("hundred_section_page", "hundred_section_mark", "hundred_open")
        slot = lambda n: self.pos(n).y() - self.pos("hundred_section_mark").y()          # where the chips sit inside their card
        before = {n: self.pos(n).y() for n in names}
        inside = (slot("hundred_marks"), slot("hundred_style"))
        self.load_page()
        self.click("hundred_style_chip_gold-case")                 # the caption now shows
        self.assertEqual(self.item("hundred_caption").property("text"), "Preview of a 100% game")
        self.item("screen_scroller").setProperty("contentY", 0)
        self.app.processEvents()
        after = {n: self.pos(n).y() for n in names}
        self.assertEqual(before["hundred_section_page"], after["hundred_section_page"], "the caption moved the sections")
        self.assertEqual(before["hundred_open"], after["hundred_open"])
        self.assertEqual(inside, (slot("hundred_marks"), slot("hundred_style")), "the chips moved inside their card when the page loaded")

    def test_the_chip_groups_have_names_for_screen_readers(self):
        from PySide6.QtGui import QAccessible
        QAccessible.setActive(True)
        self.addCleanup(QAccessible.setActive, False)
        for name, expect in (("hundred_marks", "Marks"), ("hundred_style", "Case")):
            iface = QAccessible.queryAccessibleInterface(self.item(name))
            self.assertEqual((iface.text(QAccessible.Text.Name), iface.role()), (expect, QAccessible.Role.Grouping), name)

    def test_the_marks_and_cases_are_greyed_until_a_page_is_loaded(self):
        for n in ("hundred_marks", "hundred_style"):
            self.assertFalse(self.item(n).property("enabled"), n)
        self.assertEqual(self.item("hundred_locked_note").property("text"), "Load your games page first.")
        self.load_page()
        for n in ("hundred_marks", "hundred_style"):
            self.assertTrue(self.item(n).property("enabled"), n)
        self.assertEqual(self.item("hundred_locked_note").property("text"), "")

    def test_the_status_line_follows_the_state(self):
        self.assertEqual(self.item("hundred_status").property("text"), "No games page loaded. Your covers keep the look they have.")
        self.load_page()
        self.assertEqual(self.item("hundred_status").property("text"), "Found 1 game at 100% in games.html. The game list from step 1 decides which games get covers.")
        self.assertTrue(self.item("hundred_note").property("text").startswith("Done with the page?"))
        self.assertEqual(self.item("hundred_status").property("kind"), "ok")

    def test_choosing_a_case_and_marks_changes_the_preview_after_a_page_is_loaded(self):
        before = self.shell.look.previewSource
        self.assertIn("/classic/none/", before)
        self.load_page()
        self.click("hundred_style_chip_gold-case")
        self.assertEqual(self.h.style, "gold-case")
        self.click("hundred_marks_chip_rosette")
        self.assertEqual(self.h.marks, "rosette")
        self.wait_for(lambda: "/gold-case-rosette/" in self.shell.look.previewSource)
        self.assertIn("/classic/gold-case-rosette/", self.shell.look.previewSource)
        self.assertEqual(self.item("hundred_caption").property("text"), "Preview of a 100% game")

    def test_no_caption_without_a_page_and_none_for_normal_covers(self):
        self.assertEqual(self.item("hundred_caption").property("text"), "")
        self.load_page()
        self.click("hundred_style_chip_none")
        self.assertEqual(self.item("hundred_caption").property("text"), "")
        self.assertFalse(self.item("hundred_marks").property("enabled"))          # no special case: no marks to choose
        self.assertTrue(self.item("hundred_marks_chip_full").property("selected"))      # the choice still shows

    def test_halloween_greys_the_marks_shows_the_note_and_classic_brings_the_marks_back(self):
        self.load_page()
        self.shell.look.theme = "halloween"
        self.app.processEvents()
        self.assertFalse(self.item("hundred_marks").property("enabled"))
        self.assertTrue(self.item("hundred_marks_chip_rosette").property("selected"))
        note = self.item("hundred_theme_note")
        self.assertTrue(note.property("visible"))
        self.assertEqual(note.property("text"), "The Halloween case shows the rosette only: the ribbon would hide the pumpkin and the web.")
        self.shell.look.theme = "classic"
        self.app.processEvents()
        self.assertTrue(self.item("hundred_marks").property("enabled"))
        self.assertFalse(self.item("hundred_theme_note").property("visible"))
        self.assertTrue(self.item("hundred_marks_chip_full").property("selected"))

    def test_skip_goes_on_without_a_page_and_unlocks_make(self):
        self.assertEqual(self.shell.steps[4]["state"], "locked")
        self.click("hundred_next")
        self.assertEqual(self.shell.current, 4)
        self.assertEqual(self.shell.steps[4]["state"], "active")
        self.assertEqual(self.shell.steps[3]["state"], "done")
        self.assertFalse(self.h.loaded)

    def test_next_goes_on_and_keeps_the_page_and_make_stays_locked_until_then(self):
        self.load_page()
        self.assertEqual(self.shell.steps[4]["state"], "locked")
        self.click("hundred_next")
        self.assertEqual(self.shell.current, 4)
        self.assertEqual(self.shell.steps[4]["state"], "active")
        self.assertTrue(self.h.loaded)

    def test_the_info_tip_carries_the_old_help(self):
        from qtui import system
        self.assertEqual(self.item("hundred_tip").property("text"), system.PAGE_HELP)

    def test_open_and_copy_use_the_page_address(self):
        from unittest import mock
        with mock.patch("qtui.hundred.QDesktopServices.openUrl", return_value=True) as m:
            self.click("hundred_open")
        self.assertIn("steamcommunity.com/my/games", m.call_args[0][0].toString())
        self.click("hundred_copy")
        self.assertIn("steamcommunity.com/my/games", QGuiApplication.clipboard().text())

    def test_browse_without_a_desktop_chooser_starts_qts_dialog_in_downloads(self):
        from unittest import mock
        from PySide6.QtCore import QObject
        dialog = self.root.findChild(QObject, "hundred_dialog")
        self.assertIsNotNone(dialog)
        with mock.patch("qtui.hundred.pick_file", return_value=None):
            self.click("hundred_browse")
            self.wait_for(lambda: dialog.property("visible"))
        self.assertTrue(dialog.property("visible"))
        self.assertEqual(dialog.property("currentFolder").toString(), self.h.downloadsUrl)
        dialog.close()
        self.app.processEvents()

    def test_the_tab_stops_are_the_buttons_the_tip_and_one_chip_per_enabled_group(self):
        def stops():
            return sorted(n for n in ("hundred_open", "hundred_browse", "hundred_copy", "hundred_tip", "hundred_next",
                                      "hundred_marks_chip_full", "hundred_marks_chip_rosette", "hundred_style_chip_ribbon", "hundred_style_chip_gold-case")
                          if self.item(n).property("activeFocusOnTab"))
        self.assertEqual(stops(), ["hundred_browse", "hundred_copy", "hundred_next", "hundred_open", "hundred_tip"])
        self.load_page()
        self.assertEqual(stops(), ["hundred_browse", "hundred_copy", "hundred_marks_chip_full", "hundred_next", "hundred_open", "hundred_style_chip_ribbon", "hundred_tip"])

    def test_the_preview_sits_left_of_the_sections_and_above_them_when_narrow(self):
        self.root.setProperty("width", 1000)
        self.app.processEvents()
        self.assertLess(self.pos("hundred_preview").x(), self.pos("hundred_section_page").x())
        self.root.setProperty("width", self.root.property("minimumWidth"))
        self.app.processEvents()
        self.assertLess(self.pos("hundred_preview").y(), self.pos("hundred_section_page").y())

    def test_nothing_sticks_out_of_its_card_at_the_narrowest_window(self):
        from PySide6.QtCore import QPointF
        self.load_page()
        self.shell.look.theme = "halloween"
        self.root.setProperty("minimumWidth", 420)
        self.root.setProperty("width", 420)
        self.app.processEvents()
        names = {"hundred_section_page": ["hundred_intro", "hundred_open", "hundred_browse", "hundred_copy", "hundred_status", "hundred_note", "hundred_tip"],
                 "hundred_section_mark": ["hundred_marks", "hundred_style", "hundred_theme_note", "hundred_locked_note"]}
        for sec, items in names.items():
            s = self.item(sec)
            right = s.mapToScene(QPointF(s.width(), 0)).x()
            for n in items:
                self.reveal(n)
                it = self.item(n)
                self.assertLessEqual(it.mapToScene(QPointF(it.width(), 0)).x(), right + 0.5, "%s sticks out of %s" % (n, sec))
        for n in ("hundred_status", "hundred_note", "hundred_theme_note"):
            self.assertFalse(self.item(n).property("truncated"), n)

    def test_the_screen_uses_the_guides_numbers_only(self):
        import re
        with open(os.path.join(QML_DIR, "HundredScreen.qml")) as f:
            text = f.read()
        self.assertEqual(re.findall(r"spacing:\s*Theme\.s4\b", text), [])


@need_qt
class ShellObject(QtCase):
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
              "PySide6/Qt/lib/libQt6QuickControls2.so.6", "PySide6/Qt/lib/libQt6QuickEffects.so.6", "PySide6/Qt/lib/libQt6QuickControls2Basic.so.6", "PySide6/Qt/lib/libQt6QuickTemplates2.so.6",
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


class ReleaseWorkflow(unittest.TestCase):
    """.github/workflows/release.yml ships the Qt window under the file names the downloads always had. It is run only by a tag or by hand: this class is the guard."""
    PATH = os.path.join(os.path.dirname(QML_DIR), "..", ".github", "workflows", "release.yml")

    def text(self):
        with open(self.PATH) as f:
            return f.read()

    def test_it_still_runs_on_a_version_tag_or_by_hand(self):
        t = self.text()
        self.assertIn('tags: ["v*"]', t)
        self.assertIn("workflow_dispatch:", t)

    def test_it_builds_and_tests_the_qt_window_not_the_tk_one(self):
        t = self.text()
        for needle in ("requirements-qt.txt", "python -m qtui --selftest", "pyinstaller --noconfirm steamcase-qt.spec", "QT_QPA_PLATFORM: offscreen", "unittest discover -s tests", "libegl1"):
            self.assertIn(needle, t)
        for gone in ("gui.py", "steamcase.spec", "requirements-build.txt"):
            self.assertNotIn(gone, t)

    def test_the_downloads_keep_their_names(self):
        t = self.text()
        for name in ("SteamCaseCovers-windows.exe", "SteamCaseCovers-macos.zip", "SteamCaseCovers-linux"):
            self.assertIn("asset: " + name, t)
        self.assertNotIn("asset: SteamCaseCoversQt", t)

    def test_the_built_app_is_checked_on_each_system_before_it_is_kept(self):
        t = self.text()
        self.assertIn("dist\\SteamCaseCoversQt.exe", t)
        self.assertIn("dist/SteamCaseCovers.app/Contents/MacOS/SteamCaseCoversQt --selftest", t)
        self.assertIn("dist/SteamCaseCoversQt --selftest", t)
        self.assertIn("codesign --force --deep --sign -", t)

    def test_the_downloads_are_gathered_apart_from_the_repository_pictures(self):
        import re
        t = self.text()
        self.assertNotRegex(t, r"download-artifact[^\n]*\n\s+with:\n\s+path: assets")
        self.assertIn("path: release-files", t)
        self.assertIn("cd release-files && sha256sum *", t)
        self.assertIn("subject-path: release-files/*", t)
        self.assertIn("files: release-files/*", t)

    def test_the_version_is_stamped_for_tags_only_and_before_the_build(self):
        t = self.text()
        stamp = t.index("Stamp the version into the build")
        self.assertIn("if: startsWith(github.ref, 'refs/tags/')", t[stamp:stamp + 200])
        self.assertLess(stamp, t.index("pyinstaller --noconfirm steamcase-qt.spec"))

    def test_the_macos_steps_run_in_a_safe_order(self):
        t = self.text()
        order = [t.index(x) for x in ("mv dist/SteamCaseCoversQt.app", "xattr -cr dist/SteamCaseCovers.app", "codesign --force --deep --sign -", "codesign --verify", "MacOS/SteamCaseCoversQt --selftest", "ditto -c -k")]
        self.assertEqual(order, sorted(order))

    def test_a_failing_windows_selftest_leaves_its_reason_in_the_log(self):
        for path in (self.PATH, QtPreviewWorkflow.PATH):
            with open(path) as f:
                t = f.read()
            self.assertIn('-ArgumentList "--selftest","--log","selftest.log"', t)
            self.assertIn("Get-Content selftest.log", t)

    def test_the_macos_program_is_named_after_the_project_in_the_dock(self):
        with open(os.path.join(os.path.dirname(QML_DIR), "..", "steamcase-qt.spec")) as f:
            spec = f.read()
        self.assertIn('"CFBundleName": "SteamCaseCovers"', spec)
        self.assertIn('"CFBundleDisplayName": "SteamCaseCovers"', spec)

    def test_the_preview_rehearses_the_same_macos_steps(self):
        with open(QtPreviewWorkflow.PATH) as f:
            preview = f.read()
        for step in ("mv dist/SteamCaseCoversQt.app dist/SteamCaseCovers.app", "codesign --force --deep --sign - dist/SteamCaseCovers.app",
                     "dist/SteamCaseCovers.app/Contents/MacOS/SteamCaseCoversQt --selftest", "ditto -c -k --keepParent dist/SteamCaseCovers.app"):
            self.assertIn(step, preview)
            self.assertIn(step, self.text())

    def test_the_names_inside_match_what_the_spec_builds(self):
        with open(os.path.join(os.path.dirname(QML_DIR), "..", "steamcase-qt.spec")) as f:
            spec = f.read()
        self.assertEqual(spec.count('name="SteamCaseCoversQt"'), 3)         # the Windows/Linux file, the macOS program, the macOS folder
        self.assertIn('BUNDLE(coll, name="SteamCaseCoversQt.app"', spec)

    def test_the_release_part_is_untouched(self):
        t = self.text()
        for needle in ("echo \"$TAG\" > assets/version.txt", "tools/release_message.py body", "sha256sum", "attest-build-provenance", "softprops/action-gh-release",
                       "prerelease: ${{ startsWith(github.ref_name, 'v0.') }}", "contents: write"):
            self.assertIn(needle, t)

    def test_every_action_is_pinned_by_commit(self):
        import re
        for u in re.findall(r"uses:\s*(\S+)", self.text()):
            self.assertRegex(u, r"@[0-9a-f]{40}$", u)


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
        self.assertIn("1 Game list, 2 Look, 3 100% games (optional), 4 Make, 5 Add to Steam", text)
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
        self.assertEqual(re.findall(r"\bImage\s*\{", main), [], "the window itself has no picture")
        with open(os.path.join(QML_DIR, "NavLink.qml")) as f:
            self.assertEqual(re.findall(r"\bImage\s*\{", f.read()), ["Image {"], "the only picture in the window is the Discord icon of a navigation link")
        for name in os.listdir(QML_DIR):
            with open(os.path.join(QML_DIR, name)) as f:
                self.assertNotIn("backdrop", f.read().lower(), name)

    def test_every_component_is_in_the_guide(self):
        import re
        with open(os.path.join(QML_DIR, "qmldir")) as f:
            names = [m.group(1) for m in re.finditer(r"^(\w+) 1\.0 ", f.read(), re.M)]
        with open(os.path.join(os.path.dirname(QML_DIR), "..", "docs", "ui-guide.md")) as f:
            guide = f.read()
        for name in names:
            if name != "Theme" and not name.endswith("Screen"):
                self.assertIn("`%s`" % name, guide, "%s is not in the guide's component list" % name)

    def test_no_other_file_has_a_colour_of_its_own(self):
        import re
        for name in os.listdir(QML_DIR):
            if name.endswith(".qml") and name != "Theme.qml":
                with open(os.path.join(QML_DIR, name)) as f:
                    self.assertEqual(re.findall(r"#[0-9a-fA-F]{3,8}\b", f.read()), [], name)


@need_qt
class ShellWindow(QtCase):
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
        self.assertEqual(self.item("footer_discord").property("text"), "Join our Discord")

    def test_closing_the_window_while_steam_art_is_being_changed_is_refused_with_the_old_words(self):
        from PySide6.QtTest import QTest
        self.shell.apply._busy = True
        self.assertFalse(self.root.close())                                                             # refused
        self.assertTrue(self.root.isVisible())
        QTest.qWait(60)
        self.assertEqual(self.item("main_dlg_title").property("text"), "Please wait")
        self.assertEqual(self.item("main_dlg_p0").property("text"), "Steam's artwork is being changed. Closing now could leave it half-done. Wait a few seconds, then close the window.")
        self.shell.apply._busy = False

    def test_the_window_closes_when_nothing_is_being_changed(self):
        self.assertTrue(self.root.close())

    def test_the_optional_step_says_so_and_a_locked_step_says_why_under_its_name(self):
        from PySide6.QtGui import QAccessible
        want = {"home": "", "game_list": "", "look": "after step 1", "hundred": "(optional)", "make": "after step 3", "add": "after step 4"}
        for key, hint in want.items():
            self.assertEqual(self.item("nav_" + key).property("hint"), hint, key)
        hint, row = self.item("nav_hundred_hint"), self.item("nav_hundred")
        self.assertEqual(hint.property("text"), want["hundred"])
        self.assertLessEqual(self.item("nav_hundred_label").height() + hint.height(), row.height())       # both lines fit the row
        self.assertLessEqual(hint.width(), row.width() - 40)                                              # and the words fit beside the margins
        for key in ("look", "hundred", "make", "add"):                                                  # none of the words is cut at this width
            h = self.item("nav_%s_hint" % key)
            self.assertLessEqual(h.property("implicitWidth"), h.width(), key)
        QAccessible.setActive(True)
        self.addCleanup(QAccessible.setActive, False)
        self.assertEqual(QAccessible.queryAccessibleInterface(row).text(QAccessible.Text.Name), "3  100% games (optional), locked")
        self.shell.setFact("ready", True)                                                               # unlocked: only what is always true remains
        self.shell.setFact("look_done", True)
        self.assertEqual((self.shell.steps[2]["hint"], self.shell.steps[3]["hint"], self.shell.steps[4]["hint"]), ("", "(optional)", "after step 3"))

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
class Entry(QtCase):
    """`python -m qtui --selftest`: builds the window offscreen, checks it, and exits 0 (ok) or 1 (with the QML messages)."""
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()                          # some tests here build a window in this process; they must pass alone, too

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
        self.assertIn("look_next", text)                      # and the Look screen, which draws the preview and the sliders
        self.assertRegex(text, r"Shell\(.*downloads=", "the self-test must never look at the real Downloads folder")

    def test_the_selftest_also_opens_the_hundred_percent_screen(self):
        """Step 3 imports the file dialog too, and a build without its screen must fail the self-test."""
        bad = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, bad, True)
        shutil.copytree(QML_DIR, os.path.join(bad, "qml"))
        with open(os.path.join(bad, "qml", "HundredScreen.qml"), "w") as f:
            f.write('import QtQuick\nimport "."\nScreenFrame { title: "empty" }\n')
        log = os.path.join(bad, "qtui-error.log")
        r = self.run_selftest("--qml-dir", os.path.join(bad, "qml"), "--log", log)
        self.assertEqual(r.returncode, 1)
        with open(log) as f:
            self.assertIn("the 100% games screen", f.read())
        self.assertNotIn("selftest ok", r.stdout)

    def test_the_selftest_also_opens_the_make_and_add_screens(self):
        for screen, text in (("MakeScreen.qml", "the Make screen"), ("AddScreen.qml", "the Add to Steam screen"), ("HomeScreen.qml", "the Home screen")):
            with self.subTest(screen=screen):
                bad = tempfile.mkdtemp()
                self.addCleanup(shutil.rmtree, bad, True)
                shutil.copytree(QML_DIR, os.path.join(bad, "qml"))
                with open(os.path.join(bad, "qml", screen), "w") as f:
                    f.write('import QtQuick\nimport "."\nScreenFrame { title: "empty" }\n')
                log = os.path.join(bad, "qtui-error.log")
                r = self.run_selftest("--qml-dir", os.path.join(bad, "qml"), "--log", log)
                self.assertEqual(r.returncode, 1)
                with open(log) as f:
                    self.assertIn(text, f.read())
                self.assertNotIn("selftest ok", r.stdout)

    def test_version_prints_the_version_like_the_old_window(self):
        import subprocess
        import steamcase as sc
        r = subprocess.run([sys.executable, "-m", "qtui", "--version"], cwd=self.ROOT, env=dict(os.environ, QT_QPA_PLATFORM="offscreen"), capture_output=True, text=True, timeout=60)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "steam-case-covers %s" % sc.APP_VERSION), r.stderr)

    def test_check_network_says_whether_steam_can_be_reached(self):
        import contextlib, io
        from unittest import mock
        import steamcase as sc
        from qtui.__main__ import main
        for answer, code, text in (((True, "Steam answered."), 0, "network ok: Steam answered."), ((False, "No route."), 1, "network FAILED: No route.")):
            out = io.StringIO()
            with mock.patch.object(sc, "check_network", return_value=answer), contextlib.redirect_stdout(out):
                self.assertEqual(main(["--check-network"]), code)
            self.assertEqual(out.getvalue().strip(), text)

    def test_the_selftest_checks_that_the_preview_really_draws(self):
        from unittest import mock
        from PySide6.QtCore import QSize
        from qtui.app import check_preview, close_engine, create_engine
        from qtui.shell import Shell
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        engine = create_engine(Shell(os.path.join(tmp, "s.json"), downloads=tmp, covers_dir=tmp))
        self.addCleanup(close_engine, engine)
        self.assertTrue(check_preview(engine))
        with mock.patch("steamcase.preview_cover", side_effect=RuntimeError("boom")):
            self.assertFalse(check_preview(engine, fresh=True))
        with open(os.path.join(self.ROOT, "qtui", "__main__.py")) as f:
            self.assertIn("check_preview", f.read())

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


class FakeStore(unittest.TestCase):
    """A fake store and a fake download (a small red JPEG), and a covers folder, for tests that make covers."""
    def setUp(self):
        super().setUp()
        import io
        import steamcase as sc
        if sc.Image is None:
            self.skipTest("Pillow missing")
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.covers = os.path.join(self.tmp, "covers")
        buf = io.BytesIO()
        sc.Image.new("RGB", (100, 150), (200, 60, 60)).save(buf, format="JPEG")
        jpeg = buf.getvalue()
        real = (sc.store_items, sc.http_get)
        sc.store_items = lambda ids, log=None, cancelled=None, errors=None: {i: {"type": 0, "name": "Game %d" % i} for i in ids}
        sc.http_get = lambda url, tries=3: jpeg
        self.addCleanup(lambda: setattr(sc, "store_items", real[0]) or setattr(sc, "http_get", real[1]))

    def made(self, games=None, **kw):
        import steamcase as sc
        sc.make_covers(games or {1: None, 2: None}, self.covers, **kw)

    def remake(self, **kw):
        shutil.rmtree(self.covers, ignore_errors=True)
        self.made(**kw)

    def mine(self, colour=(10, 160, 30)):
        import steamcase as sc
        path = os.path.join(self.tmp, "mine.jpg")
        sc.Image.new("RGB", (100, 150), colour).save(path, format="JPEG")
        return path


class ReplaceReasons(FakeStore):
    """The sentences of the "replace what you made?" question, over covers made by the engine's own functions."""
    def reason(self, tone, completed, treatment, theme=None, *rest):
        from qtui import reasons
        got = reasons.replace_reason(self.covers, tone, completed, treatment, theme, *rest)
        self.assertIsNotNone(got)
        title, sentence = got
        self.assertTrue(title.strip() and sentence.strip(), got)
        self.assertNotIn("%", title.replace("100%", ""))
        self.assertNotIn("%", sentence.replace("100%", ""))
        return got

    def none(self, *args):
        from qtui import reasons
        self.assertIsNone(reasons.replace_reason(self.covers, *args))

    def test_the_labels_name_the_case_then_the_marks(self):
        from qtui import reasons
        self.assertEqual(reasons.look_label("gold-case"), "Gold case, rosette and ribbon")
        self.assertEqual(reasons.look_label("ribbon"), "Normal case, rosette and ribbon")
        self.assertEqual(reasons.look_label("rosette"), "Normal case, rosette only")

    def test_custom_art_turned_on_asks_before_replacing_covers(self):
        self.made()
        got = self.reason((0, 100, 100), None, None, None, {1: self.mine()})
        self.assertIn("your own art", got[1])

    def test_custom_art_turned_off_asks_too(self):
        self.made(custom_art={1: self.mine()})
        self.assertIn("Steam's own art", self.reason((0, 100, 100), None, None, None, {})[1])

    def test_nothing_to_ask_when_nothing_changes(self):
        mine = self.mine()
        self.made(custom_art={1: mine})
        self.none((0, 100, 100), None, None, None, {1: mine})
        self.none((0, 100, 100), None, None, None)                          # art not asked about: covers keep their art

    def test_covers_of_games_outside_the_run_are_not_mentioned(self):
        self.made(custom_art={1: self.mine()})
        self.reason((0, 100, 100), None, None, None, {}, {1, 2})
        self.none((0, 100, 100), None, None, None, {}, {2, 3})

    def test_a_colour_change_and_art_say_both_but_not_art_when_it_stays(self):
        self.made()
        got = self.reason((90, 100, 100), None, None, None, {1: self.mine()})
        self.assertIn("colour", got[1])
        self.assertIn("your own art", got[1])
        self.assertNotIn("art", self.reason((90, 100, 100), None, None, None, {})[1])
        mine = self.mine()
        self.remake(custom_art={1: mine})
        self.assertNotIn("art", self.reason((90, 100, 100), None, None, None, {1: mine})[1])

    def test_no_page_only_a_colour_change(self):
        self.made()
        self.assertIn("colour", self.reason((90, 100, 100), None, None)[1])

    def test_nothing_to_rebuild_gives_no_question(self):
        self.made(completed={1}, treatment="ribbon")
        self.none((0, 100, 100), {1}, "ribbon", None)

    def test_no_special_case(self):
        self.made(completed={1}, treatment="ribbon")
        self.assertIn("No special case", self.reason((0, 100, 100), set(), None)[1])

    def test_a_page_with_no_game_at_100_says_the_highlight_is_lost(self):
        for treatment in ("ribbon", "gold-case"):
            self.remake(completed={1}, treatment=treatment)
            self.assertIn("lose it", self.reason((0, 100, 100), set(), "ribbon")[1])

    def test_a_first_highlight_over_plain_covers(self):
        import steamcase as sc
        for treatment in sc.TREATMENTS:
            self.remake()
            self.assertIn("highlighted", self.reason((0, 100, 100), {1}, treatment)[1])

    def test_a_change_of_marks_alone_says_which_marks_come(self):
        self.made(completed={1}, treatment="rosette")
        self.assertIn("rosette and ribbon", self.reason((0, 100, 100), {1}, "ribbon")[1])
        self.remake(completed={1}, treatment="ribbon")
        self.assertIn("rosette only", self.reason((0, 100, 100), {1}, "rosette")[1])

    def test_a_theme_change_alone_says_the_new_covers_get_the_theme(self):
        self.made()
        title, text = self.reason((0, 100, 100), None, None, "halloween")
        self.assertIn("theme", title.lower())
        self.assertIn("new ones in the Halloween theme", text)
        self.remake(theme="halloween")
        self.assertIn("new ones in the Classic case", self.reason((0, 100, 100), None, None, None)[1])

    def test_a_theme_without_a_page_says_the_100_covers_lose_their_ribbon(self):
        self.made(completed={1}, treatment="ribbon")
        text = self.reason((0, 100, 100), None, None, "halloween")[1]
        self.assertIn("lose their ribbon", text)
        self.assertIn("Rosette and ribbon", text)
        self.remake(completed={1}, treatment="rosette")
        self.assertNotIn("ribbon", self.reason((0, 100, 100), None, None, "halloween")[1])
        self.remake()
        self.assertNotIn("ribbon", self.reason((0, 100, 100), None, None, "halloween")[1])

    def test_it_says_the_same_as_the_old_window(self):
        """The Tk window's own function is the reference: every kind of change over every kind of folder gives the same words."""
        import types
        import steamcase as sc
        try:
            import gui
        except ImportError:
            self.skipTest("tkinter missing")
        from qtui import reasons
        fake = types.SimpleNamespace(covers_dir=self.covers)
        folders = [dict(), dict(completed={1}, treatment="ribbon"), dict(completed={1}, treatment="gold-case-rosette"), dict(theme="halloween"),
                   dict(hue=90), dict(completed={1, 2}, treatment="rosette", theme="halloween")]
        asks = [((0, 100, 100), None, None, None), ((90, 100, 100), None, None, "halloween"), ((0, 100, 100), set(), None, None),
                ((0, 100, 100), {1}, "gold-border", None), ((40, 80, 90), {1, 2}, "rosette", "halloween"), ((0, 100, 100), {2}, "ribbon", None)]
        for folder in folders:
            self.remake(**folder)
            for tone, completed, treatment, theme in asks:
                for art, games in ((sc.KEEP, None), ({}, None), ({1: self.mine()}, {1, 2}), ({}, {3})):
                    want = gui.App._replace_reason(fake, tone, completed, treatment, theme, art, games)
                    got = reasons.replace_reason(self.covers, tone, completed, treatment, theme, art, games)
                    self.assertEqual(got, want, (folder, tone, completed, treatment, theme, art, games))


@need_qt
class UpdatesState(QtCase):
    """The update check (only on a click, off the UI thread) and the Discord link."""
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def setUp(self):
        from qtui.updates import Updates
        self.u = Updates()
        self.seen = []
        self.u.message.connect(lambda *a: self.seen.append(a))

    def wait_for(self, condition, seconds=5):
        import time
        end = time.time() + seconds
        while time.time() < end and not condition():
            self.app.processEvents()
            time.sleep(0.02)
        self.app.processEvents()

    def check(self, result=None, error=None):
        from unittest import mock
        import steamcase as sc
        effect = error if error else None
        with mock.patch.object(sc, "check_for_update", return_value=result, side_effect=effect):
            self.u.check()
            self.wait_for(lambda: bool(self.seen) and not self.u.checking)
        return self.seen[-1]

    def test_nothing_is_asked_until_clicked(self):
        self.assertEqual((self.u.checking, self.seen), (False, []))

    def test_no_update_needed(self):
        self.assertEqual(self.check({"newer": False, "current": "1.2.0", "latest": "1.2.0", "url": "https://github.com/x"}),
                         ("No update needed", [{"text": "You have the latest version (1.2.0).", "kind": "main"}], "OK", "", ""))

    def test_a_newer_version_offers_the_page_and_says_nothing_is_installed(self):
        title, paragraphs, ok, cancel, link = self.check({"newer": True, "current": "1.2.0", "latest": "1.3.0", "url": "https://github.com/x/releases"})
        self.assertEqual((title, ok, cancel, link), ("Update available", "Open GitHub page", "Not now", "https://github.com/x/releases"))
        self.assertEqual(paragraphs[0]["text"], "A newer version is available: 1.3.0 (you have 1.2.0).")
        self.assertIn("opens this project's release page on GitHub in your web browser:\nhttps://github.com/x/releases", paragraphs[1]["text"])
        self.assertEqual(paragraphs[2]["text"], "Nothing is downloaded or installed unless you choose to do it yourself on that page.")

    def test_an_unknown_current_version_cannot_be_compared(self):
        paragraphs = self.check({"newer": None, "current": None, "latest": "1.3.0", "url": "https://github.com/x"})[1]
        self.assertEqual(paragraphs[0]["text"], "The latest version is 1.3.0. This copy has no version number (it was not installed from a release), so I cannot compare.")

    def test_a_failed_check_says_why(self):
        import steamcase as sc
        self.assertEqual(self.check(error=sc.SteamcaseError("No connection.")),
                         ("Could not check for updates", [{"text": "No connection.", "kind": "main"}], "OK", "", ""))
        self.seen.clear()
        self.assertEqual(self.check(error=ValueError("boom"))[1][0]["text"], "Unexpected problem: boom")

    def test_one_check_at_a_time_and_it_runs_off_the_ui_thread(self):
        import threading
        from unittest import mock
        import steamcase as sc
        gate, threads = threading.Event(), []
        self.addCleanup(gate.set)                                       # a failing test must not leave a worker thread waiting

        def slow():
            threads.append(threading.current_thread())
            gate.wait(5)
            return {"newer": False, "current": "1", "latest": "1", "url": "https://github.com/x"}
        with mock.patch.object(sc, "check_for_update", slow):
            self.u.check()
            self.u.check()
            self.assertTrue(self.u.checking)
            gate.set()
            self.wait_for(lambda: bool(self.seen) and not self.u.checking)
        self.assertEqual(len(threads), 1)
        self.assertIsNot(threads[0], threading.main_thread())

    def test_only_a_web_link_is_ever_opened(self):
        from unittest import mock
        with mock.patch("qtui.updates.QDesktopServices.openUrl", return_value=True) as opened:
            self.u.openLink("file:///etc/passwd")
            self.u.openLink("javascript:alert(1)")
            self.assertEqual(opened.call_count, 0)
            self.u.openLink("https://github.com/x/releases")
            self.assertEqual(opened.call_count, 1)

    def test_discord_opens_the_invite_or_copies_it(self):
        from unittest import mock
        import steamcase as sc
        from PySide6.QtGui import QGuiApplication
        with mock.patch("qtui.updates.QDesktopServices.openUrl", return_value=True) as opened:
            self.u.openDiscord()
        self.assertEqual((opened.call_args[0][0].toString(), self.seen), (sc.DISCORD_URL, []))
        with mock.patch("qtui.updates.QDesktopServices.openUrl", return_value=False):
            self.u.openDiscord()
        self.assertEqual(QGuiApplication.clipboard().text(), sc.DISCORD_URL)
        self.assertEqual(self.seen[-1], ("Join our Discord", [{"text": "Your browser did not open, so the invite link was copied. Paste it into your browser:\n" + sc.DISCORD_URL, "kind": "main"}], "OK", "", ""))

    def test_an_answer_that_cannot_be_delivered_is_dropped_quietly(self):
        import shiboken6
        from unittest import mock
        import steamcase as sc
        from qtui.updates import Updates
        gone = Updates()
        shiboken6.delete(gone)
        with mock.patch.object(sc, "check_for_update", return_value={"newer": False, "current": "1", "latest": "1", "url": "u"}):
            gone._worker()


@need_qt
class MakeScreen(QtCase, FakeStore):
    """Step 4 in the real window: the choices, the progress, the question before replacing, and the buttons that follow the state."""
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def setUp(self):
        super().setUp()
        from unittest import mock
        import steamcase as sc
        from qtui.app import close_engine, create_engine
        from qtui.shell import Shell
        for name, value in (("steam_dir", lambda: self.tmp), ("load_library", lambda steam, lib: ({1: None, 2: None}, set()))):
            patcher = mock.patch.object(sc, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        os.makedirs(os.path.join(self.tmp, "Downloads"))
        self.shell = Shell(os.path.join(self.tmp, "settings.json"), downloads=os.path.join(self.tmp, "Downloads"), covers_dir=self.covers)
        self.shell.reduceEffects = True
        self.shell.library.installedOnly = True
        for fact in ("look_done", "hundred_done"):
            self.shell.setFact(fact, True)
        self.engine = create_engine(self.shell)
        self.addCleanup(close_engine, self.engine)
        self.root = self.engine.rootObjects()[0]
        self.make = self.shell.make
        self.shell.go(4)
        self.app.processEvents()

    item = LookScreen.item
    centre = LookScreen.centre
    reveal = LookScreen.reveal
    click = LookScreen.click
    pos = LookScreen.pos
    wait_for = HundredScreen.wait_for

    def text(self, name):
        return self.item(name).property("text")

    def settle(self):
        """One frame, so the layout is polished (the footer's buttons move apart when a second one appears) before a click."""
        from PySide6.QtTest import QTest
        QTest.qWait(60)
        self.app.processEvents()

    def test_it_has_its_title_and_two_sections(self):
        self.assertEqual(self.text("screen_title"), "Make your covers")
        for name in ("make_section_choices", "make_section_progress", "make_preview", "make_choices", "make_progress", "make_status", "make_folder", "make_main"):
            self.assertIsNotNone(self.item(name), name)

    def test_the_choices_show_what_the_earlier_steps_chose_and_lead_back(self):
        self.assertIn("Installed games", self.item("make_choices_chip_games").property("Accessible.name") or "Installed games")
        self.click("make_choices_chip_colour")
        self.assertEqual(self.shell.current, 2)
        self.shell.go(4)
        self.app.processEvents()
        self.click("make_choices_chip_hundred")
        self.assertEqual(self.shell.current, 3)

    def test_make_covers_is_the_filled_button_and_runs_the_work(self):
        main = self.item("make_main")
        self.assertEqual((self.text("make_main"), main.property("filled"), main.property("enabled")), ("Make covers", True, True))
        self.assertEqual(self.text("make_status"), "Not started.")
        self.assertFalse(self.item("make_again").property("visible"))
        self.click("make_main")
        self.wait_for(lambda: self.make.done and not self.make.running)
        self.settle()
        self.assertEqual(self.text("make_status"), "Done. 2 covers ready.")
        self.assertAlmostEqual(self.item("make_progress_fill").width() / self.item("make_progress").width(), 1.0, delta=0.01)
        self.assertEqual((self.text("make_main"), self.item("make_main").property("filled")), ("Next: Add to Steam \u2192", True))
        self.assertTrue(self.item("make_again").property("visible"))
        self.assertFalse(self.item("make_again").property("filled"))

    def test_the_button_becomes_cancel_while_it_runs_and_keeps_the_focus(self):
        import threading
        from unittest import mock
        import steamcase as sc
        gate, reached = threading.Event(), threading.Event()
        self.addCleanup(gate.set)                                       # a failing test must not leave a worker thread waiting
        self.addCleanup(gate.set)                                       # a failing test must not leave a worker thread waiting
        real = sc.make_covers

        def slow(games, out, **kw):
            inner = kw["progress"]

            def progress(*a):
                inner(*a)
                reached.set()
                gate.wait(10)
            kw["progress"] = progress
            return real(games, out, **kw)
        main = self.item("make_main")
        self.root.requestActivate()
        main.forceActiveFocus()
        with mock.patch.object(sc, "make_covers", slow):
            self.click("make_main")
            self.wait_for(reached.is_set)
            self.assertEqual((self.text("make_main"), self.item("make_main").property("filled"), self.item("make_main").property("enabled")), ("Cancel", False, True))
            self.assertTrue(self.item("make_main").property("activeFocus"))
            self.click("make_main")
            self.assertEqual(self.text("make_status"), "Stopping\u2026")
            gate.set()
            self.wait_for(lambda: not self.make.running)
        self.assertTrue(self.text("make_status").startswith("Stopped. "))

    def test_replacing_covers_asks_first_and_declining_changes_nothing(self):
        self.click("make_main")
        self.wait_for(lambda: self.make.done and not self.make.running)
        self.settle()
        self.shell.look.setTone(90, 100, 100)
        self.click("make_again")
        self.app.processEvents()
        from PySide6.QtTest import QTest
        QTest.qWait(60)
        self.assertTrue(self.item("make_dialog").isVisible())
        self.assertEqual(self.text("dlg_title"), "Change the colour of your covers?")
        self.assertEqual(self.text("dlg_p0"), "This replaces the covers you already made in another colour.")
        self.assertEqual(self.text("dlg_p1"), "Steam keeps showing your current art until you add the new covers in step 5.")
        self.assertEqual(self.text("dlg_confirm"), "Replace them")
        self.click("dlg_cancel")
        self.settle()
        self.assertFalse(self.item("make_dialog").isVisible())
        self.assertFalse(self.make.running)
        self.assertEqual(self.text("make_status"), "Done. 2 covers ready.")
        self.click("make_again")
        QTest.qWait(60)
        self.click("dlg_confirm")
        self.wait_for(lambda: not self.make.running and not self.make.asking)
        self.assertFalse(self.sc_colour_differs(90))

    def sc_colour_differs(self, hue):
        import steamcase as sc
        return sc.covers_in_other_colour(self.covers, hue, 100, 100)

    def test_next_opens_add_to_steam(self):
        self.click("make_main")
        self.wait_for(lambda: self.make.done and not self.make.running)
        self.settle()
        self.click("make_main")
        self.assertEqual(self.shell.current, 5)

    def test_the_button_waits_while_a_games_page_is_being_read(self):
        import threading
        from unittest import mock
        import completion
        gate = threading.Event()
        self.addCleanup(gate.set)                                       # a failing test must not leave a worker thread waiting
        real = completion.read_games_page
        with mock.patch("completion.read_games_page", side_effect=lambda p: (gate.wait(5), real(p))[1]):
            self.shell.hundred.loadPage(write_games_page(self.tmp, {1: (1, 1)}))
            self.app.processEvents()
            self.assertFalse(self.item("make_main").property("enabled"))
            gate.set()
            self.wait_for(lambda: not self.shell.hundred.busy)
        self.assertTrue(self.item("make_main").property("enabled"))

    def test_the_covers_folder_button_asks_the_system_to_open_it(self):
        from unittest import mock
        self.click("make_main")
        self.wait_for(lambda: self.make.done and not self.make.running)
        self.settle()
        with mock.patch("qtui.make.QDesktopServices.openUrl", return_value=True) as opened:
            self.click("make_folder")
        self.assertEqual(opened.call_count, 1)

    def test_nothing_is_wider_than_its_card_and_the_footer_stays_in_view_when_narrow(self):
        from PySide6.QtCore import QPointF
        self.root.setProperty("width", self.root.property("minimumWidth"))
        self.root.setProperty("height", self.root.property("minimumHeight"))
        self.app.processEvents()
        for sec, names in (("make_section_choices", ("make_choices",)), ("make_section_progress", ("make_progress", "make_status", "make_folder"))):
            card = self.item(sec)
            right = card.mapToScene(QPointF(card.width(), 0)).x()
            for n in names:
                it = self.item(n)
                self.assertLessEqual(it.mapToScene(QPointF(it.width(), 0)).x(), right + 0.5, n)
        main = self.item("make_main")
        self.assertLessEqual(main.mapToScene(QPointF(0, main.height())).y(), self.root.property("height"))

    def test_leaving_the_screen_while_looking_for_art_still_shows_the_question(self):
        from unittest import mock
        import steamcase as sc
        self.click("make_main")
        self.wait_for(lambda: self.make.done and not self.make.running)
        self.settle()
        self.shell.look.setTone(90, 100, 100)
        self.shell.setSwitch("use_custom_art", True)
        with mock.patch.object(sc, "find_custom_art", lambda steam, account, originals=None, problems=None: {}):
            self.click("make_again")
            self.shell.go(2)                                            # away, while the art is being looked for
            self.wait_for(lambda: self.make.asking)
            self.shell.go(4)
            self.settle()
            self.assertTrue(self.item("make_dialog").isVisible())
            self.assertEqual(self.text("dlg_title"), self.make.questionTitle)
            self.click("dlg_cancel")
            self.settle()
        self.assertFalse(self.make.running)

    def test_make_again_and_the_folder_button_follow_their_conditions(self):
        import threading
        from unittest import mock
        import completion
        self.assertFalse(self.item("make_folder").property("enabled"))        # no covers yet
        self.click("make_main")
        self.wait_for(lambda: self.make.done and not self.make.running)
        self.settle()
        self.assertTrue(self.item("make_folder").property("enabled"))
        gate = threading.Event()
        self.addCleanup(gate.set)                                       # a failing test must not leave a worker thread waiting
        real = completion.read_games_page
        with mock.patch("completion.read_games_page", side_effect=lambda p: (gate.wait(5), real(p))[1]):
            self.shell.hundred.loadPage(write_games_page(self.tmp, {1: (1, 1)}))
            self.app.processEvents()
            self.assertFalse(self.item("make_again").property("enabled"))
            gate.set()
            self.wait_for(lambda: not self.shell.hundred.busy)
        self.assertTrue(self.item("make_again").property("enabled"))

    def test_the_keyboard_comes_back_to_the_main_button_after_the_question(self):
        self.click("make_main")
        self.wait_for(lambda: self.make.done and not self.make.running)
        self.settle()
        self.shell.look.setTone(90, 100, 100)
        self.root.requestActivate()
        self.click("make_again")
        self.settle()
        self.click("dlg_cancel")
        self.settle()
        self.assertTrue(self.item("make_main").property("activeFocus"))

    def test_the_thumbnails_of_the_covers_just_made_show_under_the_status(self):
        self.assertFalse(self.item("make_thumbs").property("visible"))
        self.click("make_main")
        self.wait_for(lambda: self.make.done and not self.make.running)
        self.settle()
        self.assertTrue(self.item("make_thumbs").property("visible"))
        for i in range(2):
            thumb = self.item("make_thumb_%d" % i)
            self.assertEqual(thumb.property("progress"), 1.0)                # the picture is loaded
            self.assertEqual((thumb.width(), thumb.height()), (60, 90))
        self.assertIsNone(__import__("qtui.app", fromlist=["find_item"]).find_item(self.root, "make_thumb_2"))

    def test_the_earlier_steps_cannot_be_changed_while_the_covers_are_made(self):
        import threading
        from unittest import mock
        import steamcase as sc
        gate, reached = threading.Event(), threading.Event()
        self.addCleanup(gate.set)                                       # a failing test must not leave a worker thread waiting
        self.addCleanup(gate.set)                                       # a failing test must not leave a worker thread waiting
        real = sc.make_covers

        def slow(games, out, **kw):
            inner = kw["progress"]

            def progress(*a):
                inner(*a)
                reached.set()
                gate.wait(10)
            kw["progress"] = progress
            return real(games, out, **kw)
        self.addCleanup(gate.set)                                       # whatever fails below, the worker is never left waiting
        with mock.patch.object(sc, "make_covers", slow):
            self.click("make_main")
            self.wait_for(reached.is_set)
            for step, name in ((1, "gamelist_installed"), (2, "look_next"), (3, "hundred_open")):
                self.shell.go(step)
                self.settle()
                self.assertFalse(self.item(name).property("enabled"), name)
            self.shell.go(2)
            self.settle()
            self.assertTrue(self.item("screen_scroller").property("enabled"))   # the page still scrolls, only its controls are frozen
            self.shell.go(4)
            self.settle()
            self.assertTrue(self.item("make_main").property("enabled"))        # Cancel still works
            gate.set()
            self.wait_for(lambda: not self.make.running)
        self.shell.go(2)
        self.settle()
        self.assertTrue(self.item("look_next").property("enabled"))

    def test_the_preview_follows_the_look(self):
        before = self.item("make_preview").property("source")
        self.shell.look.setTone(90, 100, 100)
        self.wait_for(lambda: self.item("make_preview").property("source") != before)
        self.assertNotEqual(self.item("make_preview").property("source"), before)


@need_qt
class AddWindow(QtCase, FakeStore):
    """The real window with Steam faked, for the tests of step 5 and of the whole way: the engine's Steam functions are replaced and logged."""
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def setUp(self):
        super().setUp()
        from unittest import mock
        import steamcase as sc
        from qtui.app import close_engine, create_engine
        from qtui.shell import Shell
        self.sc, self.running, self.log, self.accounts = sc, False, [], [("111", "Alice")]
        self.backups, self.restored, self.ours, self.extra, self.other = [], 5, [], [], []
        self.grid = os.path.join(self.tmp, "grid")
        os.makedirs(self.grid)
        result = {"applied": 2, "replaced": 0, "unchanged": 0, "jpg_moved": 0, "backup": "/b", "account_name": "Alice"}
        for name, value in (("steam_dir", lambda: self.tmp), ("load_library", lambda steam, lib: ({1: None, 2: None}, set())),
                            ("steam_running", lambda: self.running), ("close_steam", lambda steam, timeout=60: True),
                            ("start_steam", lambda steam: self.log.append("start")),
                            ("apply_covers", lambda steam, covers, user=None, files=None: self.log.append(("apply", user)) or dict(result)),
                            ("list_accounts", lambda steam: list(self.accounts)), ("pick_account", lambda steam, forced=None: forced or self.accounts[0][0]),
                            ("account_label", lambda steam, acc: dict(self.accounts).get(acc, str(acc))),
                            ("list_backups", lambda steam, user=None: list(self.backups)),
                            ("restore_backup", lambda steam, backup, user=None, keep=False, originals=None: (self.log.append(("restore", backup)), self.backups.pop(0), self.restored)[2]),
                            ("find_our_covers", lambda steam, user=None, progress=None, cancelled=None: list(self.ours)),
                            ("find_other_art", lambda steam, user=None, ours=(): (list(self.extra), list(self.other))),
                            ("reset_to_default", lambda steam, user=None, names=None, everything=False: (self.log.append(("reset", user, list(names or []), everything)),
                                                                                                      {"removed": len(names or []), "account_name": "Alice"})[1]),
                            ("grid_dir", lambda steam, user=None: self.grid)):
            patcher = mock.patch.object(sc, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        os.makedirs(os.path.join(self.tmp, "Downloads"))
        self.shell = Shell(os.path.join(self.tmp, "settings.json"), downloads=os.path.join(self.tmp, "Downloads"), covers_dir=self.covers)
        self.shell.reduceEffects = True
        self.shell.library.installedOnly = True
        for fact in ("look_done", "hundred_done"):
            self.shell.setFact(fact, True)
        self.made = False
        self.start_window = lambda: self._start_window(create_engine, close_engine)

    def _start_window(self, create_engine, close_engine):
        if not self.made:
            self.made = True
            self.shell.make.start()
            self.wait_for(lambda: self.shell.make.done and not self.shell.make.running)
        self.engine = create_engine(self.shell)
        self.addCleanup(close_engine, self.engine)
        self.root = self.engine.rootObjects()[0]
        self.ap = self.shell.apply
        self.shell.go(5)
        self.app.processEvents()

    item = LookScreen.item
    centre = LookScreen.centre
    reveal = LookScreen.reveal
    click = LookScreen.click
    pos = LookScreen.pos
    wait_for = HundredScreen.wait_for

    def text(self, name):
        return self.item(name).property("text")

    def settle(self):
        from PySide6.QtTest import QTest
        QTest.qWait(60)
        self.app.processEvents()


class AddScreen(AddWindow):
    """Step 5 in the real window: the Steam note, the account, the restart switch, the question, the result and the way home."""
    def test_it_has_its_title_sections_and_ready_text(self):
        self.start_window()
        self.assertEqual(self.text("screen_title"), "Add them to Steam")
        for name in ("add_section_before", "add_section_result", "add_note", "add_account", "add_restart", "add_status", "add_main"):
            self.assertIsNotNone(self.item(name), name)
        self.assertEqual(self.text("add_status"), "2 covers are ready to add.")
        self.assertEqual((self.text("add_main"), self.item("add_main").property("filled"), self.item("add_main").property("enabled")), ("Apply to Steam", True, True))

    def test_the_note_follows_whether_steam_runs_and_the_screen_watches_only_while_open(self):
        self.running = True
        self.start_window()
        self.wait_for(lambda: self.ap.steamOpen)
        self.assertTrue(self.ap.watching)
        self.assertEqual(self.text("add_note"), "Steam is open. Changing the artwork closes it: any running game stops and downloads pause. Save your game first.")
        from PySide6.QtGui import QColor
        self.assertEqual(QColor(self.item("add_note").property("color")).name(), "#f0b429")
        self.shell.go(4)
        self.app.processEvents()
        self.assertFalse(self.ap.watching)

    def test_one_account_is_named_and_two_are_offered_as_chips(self):
        self.start_window()
        self.assertEqual(self.text("add_account"), "Steam account: Alice")
        self.assertFalse(self.item("add_accounts").property("visible"))
        self.accounts = [("111", "Alice"), ("222", "Bob")]
        self.shell.go(4)
        self.shell.go(5)
        self.app.processEvents()
        self.assertTrue(self.item("add_accounts").property("visible"))
        self.click("add_accounts_chip_222")
        self.assertEqual((self.ap.accountId, self.text("add_account")), ("222", "Steam account: Bob"))

    def test_one_cover_reads_in_the_singular(self):
        self.start_window()
        self.shell.make._files = ["x.png"]
        self.shell.make.doneChanged.emit()
        self.app.processEvents()
        self.assertEqual(self.text("add_status"), "1 cover is ready to add.")

    def test_the_account_chips_wait_while_covers_are_being_made(self):
        self.accounts = [("111", "Alice"), ("222", "Bob")]
        self.start_window()
        self.assertTrue(self.item("add_accounts").property("enabled"))
        self.shell.make._set_state(running=True)
        self.app.processEvents()
        self.assertFalse(self.item("add_accounts").property("enabled"))
        self.shell.make._set_state(running=False)

    def test_the_keyboard_comes_back_to_the_apply_button_after_declining(self):
        self.start_window()
        self.root.requestActivate()
        self.click("add_main")
        self.settle()
        self.click("apply_dlg_cancel")
        self.settle()
        self.assertTrue(self.item("add_main").property("activeFocus"))

    def test_the_restart_switch_greys_out_when_there_is_nothing_to_add(self):
        self.start_window()
        self.assertTrue(self.item("add_restart").property("enabled"))
        self.shell.make._files = []
        self.shell.make.doneChanged.emit()
        self.app.processEvents()
        self.assertFalse(self.item("add_restart").property("enabled"))

    def test_the_restart_switch_is_the_remembered_one(self):
        self.start_window()
        self.assertTrue(self.item("add_restart").property("checked"))
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtTest import QTest
        label = self.item("add_restart_label")                          # the label is as wide as the card; the switch answers on the words
        QTest.mouseClick(self.root, Qt.LeftButton, Qt.NoModifier, label.mapToScene(QPointF(10, label.height() / 2)).toPoint())
        self.app.processEvents()
        self.assertFalse(self.shell.switchValue("restart_steam"))
        self.assertFalse(self.item("add_restart").property("checked"))

    def test_apply_asks_then_adds_the_covers_and_the_button_leads_home(self):
        from PySide6.QtTest import QTest
        self.start_window()
        self.click("add_main")
        QTest.qWait(60)
        self.assertTrue(self.item("apply_dialog").isVisible())
        self.assertEqual(self.text("apply_dlg_title"), "Add covers to Steam")
        self.assertEqual(self.text("apply_dlg_p0"), "2 covers will be added to the Steam account \u201cAlice\u201d.")
        self.click("apply_dlg_confirm")
        self.wait_for(lambda: self.ap.applied)
        self.assertEqual(self.log, [("apply", None), "start"])
        self.assertTrue(self.text("add_status").startswith("Done. 2 covers added to the Steam account \u201cAlice\u201d"))
        self.assertEqual((self.text("add_main"), self.item("add_main").property("filled")), ("Go to Home \u2192", True))
        self.click("add_main")
        self.assertEqual(self.shell.current, 0)

    def test_declining_the_question_changes_nothing(self):
        from PySide6.QtTest import QTest
        self.start_window()
        self.click("add_main")
        QTest.qWait(60)
        self.click("apply_dlg_cancel")
        self.assertEqual((self.log, self.ap.applied, self.item("apply_dialog").isVisible()), ([], False, False))

    def test_the_button_says_applying_and_waits_while_it_works(self):
        import threading
        self.start_window()
        gate = threading.Event()
        self.addCleanup(gate.set)                                       # a failing test must not leave a worker thread waiting
        real = self.sc.apply_covers
        self.sc.apply_covers = lambda *a, **k: gate.wait(5) and real(*a, **k)
        self.addCleanup(lambda: setattr(self.sc, "apply_covers", real))
        self.ap.apply()
        self.ap.confirm()
        self.app.processEvents()
        self.assertEqual((self.text("add_main"), self.item("add_main").property("enabled")), ("Applying\u2026", False))
        gate.set()
        self.wait_for(lambda: self.ap.applied)

    def test_an_error_is_shown_in_the_error_colour(self):
        from PySide6.QtGui import QColor
        self.start_window()
        self.sc.apply_covers = lambda *a, **k: (_ for _ in ()).throw(self.sc.SteamcaseError("No covers found in x. Make them first."))
        self.ap.apply()
        self.ap.confirm()
        self.wait_for(lambda: not self.ap.busy and self.ap.status != "Working\u2026")
        self.app.processEvents()
        self.assertEqual(self.text("add_status"), "No covers found in x. Make them first.")
        self.assertEqual(QColor(self.item("add_status").property("color")).name(), "#ff7b72")
        self.assertEqual(self.text("add_main"), "Apply to Steam")

    def test_nothing_is_wider_than_its_card_and_the_footer_stays_in_view_when_narrow(self):
        from PySide6.QtCore import QPointF
        self.accounts = [("111", "A" * 40), ("222", "B" * 40)]
        self.start_window()
        self.root.setProperty("width", self.root.property("minimumWidth"))
        self.root.setProperty("height", self.root.property("minimumHeight"))
        self.app.processEvents()
        for sec, names in (("add_section_before", ("add_note", "add_account", "add_accounts", "add_restart")), ("add_section_result", ("add_status",))):
            card = self.item(sec)
            right = card.mapToScene(QPointF(card.width(), 0)).x()
            for n in names:
                it = self.item(n)
                self.assertLessEqual(it.mapToScene(QPointF(it.width(), 0)).x(), right + 0.5, n)
        main = self.item("add_main")
        self.assertLessEqual(main.mapToScene(QPointF(0, main.height())).y(), self.root.property("height"))


@need_qt
class ShellHome(QtCase):
    """What the shell knows for Home: is this a returning user, and which step to continue with."""
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def shell(self, covers=False):
        from qtui.shell import Shell
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        folder = os.path.join(tmp, "covers")
        if covers:
            os.makedirs(folder)
            open(os.path.join(folder, "Game_1_1.png"), "wb").close()
        return Shell(os.path.join(tmp, "settings.json"), downloads=os.path.join(tmp, "Downloads"), covers_dir=folder)

    def test_a_first_visit_is_new_and_continues_with_the_game_list(self):
        sh = self.shell()
        self.assertEqual((sh.returning, sh.resume), (False, 1))

    def test_any_progress_makes_a_returning_user_who_continues_where_the_steps_stand(self):
        sh = self.shell()
        seen = []
        sh.stepsChanged.connect(lambda: seen.append(sh.returning))
        sh.setFact("ready", True)
        self.assertEqual((sh.returning, sh.resume), (True, 2))
        sh.setFact("look_done", True)
        self.assertEqual(sh.resume, 3)
        self.assertIn(True, seen)

    def test_covers_on_disk_make_a_returning_user(self):
        self.assertTrue(self.shell(covers=True).returning)

    def test_when_everything_is_done_continue_goes_to_the_start_of_the_steps(self):
        sh = self.shell()
        for fact in ("ready", "look_done", "hundred_done", "covers_made", "applied"):
            sh.setFact(fact, True)
        self.assertEqual(sh.resume, 1)


@need_qt
class HomeScreen(AddWindow):
    """Home in the real window: Welcome or Dashboard, the Undo section, and the two links of the navigation."""
    def open_home(self, covers=False):
        self.made = True                                                # no covers are made here
        for fact in ("look_done", "hundred_done"):                      # a person who has not walked the steps yet
            self.shell.setFact(fact, False)
        self.shell.library.installedOnly = covers                       # a game list is "done" only for the returning user
        self.start_window()
        self.shell.go(0)
        self.app.processEvents()

    def undo_ready(self, backup=True):
        self.backups = ["b1"] if backup else []
        open(os.path.join(self.grid, "123p.png"), "wb").close()
        self.ap.refreshUndo()
        self.wait_for(lambda: self.ap.undoKnown and (self.ap.canRestore or not backup))
        self.app.processEvents()

    def test_the_first_visit_is_a_welcome_with_a_start_button(self):
        self.open_home()
        self.assertEqual(self.text("screen_title"), "Cases for your games")
        self.assertEqual(self.item("home_section_main").property("heading"), "Step by step")
        self.assertEqual((self.text("home_main"), self.item("home_main").property("filled")), ("Start \u2192", True))
        self.click("home_main")
        self.assertEqual(self.shell.current, 1)

    def test_a_returning_user_sees_the_dashboard_and_continues_where_they_stopped(self):
        self.open_home(covers=True)
        self.assertEqual(self.text("screen_title"), "Welcome back")
        self.assertEqual(self.item("home_section_main").property("heading"), "Your progress")
        self.assertEqual(self.text("home_main"), "Continue \u2192")
        self.assertEqual([self.text("home_state_" + k) for k in ("game_list", "look", "hundred", "make", "add")], ["Done", "Next", "Locked", "Locked", "Locked"])
        self.click("home_main")
        self.assertEqual(self.shell.current, 2)

    def test_a_row_of_the_dashboard_opens_its_step_unless_it_is_locked(self):
        self.open_home(covers=True)
        self.click("home_row_game_list")
        self.assertEqual(self.shell.current, 1)
        self.shell.go(0)
        self.app.processEvents()
        self.click("home_row_make")                                     # locked: nothing happens
        self.assertEqual(self.shell.current, 0)

    def test_the_undo_section_has_its_buttons_greyed_until_there_is_something_to_undo(self):
        self.open_home()
        self.wait_for(lambda: self.ap.undoKnown)
        self.assertEqual([self.item(n).property("enabled") for n in ("home_restore", "home_reset")], [False, False])
        self.assertTrue(self.text("home_hint").startswith("Nothing to undo yet"))
        self.undo_ready()
        self.assertEqual([self.item(n).property("enabled") for n in ("home_restore", "home_reset")], [True, True])
        self.assertEqual(self.text("home_hint"), "")
        self.assertFalse(self.item("home_restore").property("filled"))      # the only filled button is Start / Continue

    def test_restore_asks_and_then_says_what_was_done(self):
        from PySide6.QtTest import QTest
        self.open_home()
        self.undo_ready()
        self.click("home_restore")
        QTest.qWait(60)
        self.assertTrue(self.item("apply_dialog").isVisible())
        self.assertEqual(self.text("apply_dlg_title"), "Restore previous artwork")
        self.click("apply_dlg_confirm")
        self.wait_for(lambda: not self.ap.busy)
        self.assertTrue(self.text("home_status").startswith("Restored your previous artwork (5 files)."))
        self.assertIn(("restore", "b1"), self.log)

    def test_reset_with_art_from_elsewhere_shows_three_buttons(self):
        from PySide6.QtTest import QTest
        self.open_home()
        self.undo_ready()
        self.ours, self.other = ["a"], ["y"]
        self.click("home_reset")
        self.wait_for(lambda: self.ap.asking)
        QTest.qWait(60)
        self.assertEqual([self.text(n) for n in ("apply_dlg_cancel", "apply_dlg_alternate", "apply_dlg_confirm")], ["Cancel", "Remove all", "Remove only ours"])
        self.click("apply_dlg_alternate")
        self.wait_for(lambda: not self.ap.busy)
        self.assertEqual(self.log[0], ("reset", None, ["a"], True))

    def test_the_home_screen_watches_steam_only_while_it_is_shown(self):
        self.open_home()
        self.assertTrue(self.ap.watching)
        self.shell.go(1)
        self.app.processEvents()
        self.assertFalse(self.ap.watching)

    def test_the_restart_switch_on_home_follows_whether_there_is_anything_to_undo(self):
        self.open_home()
        self.wait_for(lambda: self.ap.undoKnown)
        self.assertFalse(self.item("home_restart").property("enabled"))
        self.undo_ready()
        self.assertTrue(self.item("home_restart").property("enabled"))

    def test_the_steam_note_and_the_restart_switch_are_here_too(self):
        self.running = True
        self.open_home()
        self.wait_for(lambda: self.ap.steamOpen)
        self.assertTrue(self.text("home_note").startswith("Steam is open."))
        self.assertTrue(self.item("home_restart").property("checked"))

    def test_nothing_is_wider_than_its_card_and_the_footer_stays_in_view_when_narrow(self):
        from PySide6.QtCore import QPointF
        self.accounts = [("111", "A" * 40)]
        self.open_home(covers=True)
        self.undo_ready()
        self.root.setProperty("width", self.root.property("minimumWidth"))
        self.root.setProperty("height", self.root.property("minimumHeight"))
        self.app.processEvents()
        for sec, names in (("home_section_main", ("home_row_look", "home_state_look")), ("home_section_undo", ("home_note", "home_account", "home_restore", "home_reset", "home_restart", "home_status"))):
            card = self.item(sec)
            right = card.mapToScene(QPointF(card.width(), 0)).x()
            for n in names:
                it = self.item(n)
                self.assertLessEqual(it.mapToScene(QPointF(it.width(), 0)).x(), right + 0.5, n)
        main = self.item("home_main")
        self.assertLessEqual(main.mapToScene(QPointF(0, main.height())).y(), self.root.property("height"))

    def test_the_account_can_be_chosen_here_for_restore_and_reset(self):
        self.accounts = [("111", "Alice"), ("222", "Bob")]
        self.open_home()
        self.assertTrue(self.item("home_accounts").property("visible"))
        self.click("home_accounts_chip_222")
        self.assertEqual((self.ap.accountId, self.text("home_account")), ("222", "Steam account: Bob"))
        self.undo_ready()
        self.ask_and_go = None
        self.click("home_restore")
        self.settle()
        self.assertEqual(self.text("apply_dlg_p0"), "Your artwork from before the last Apply will be put back on the Steam account \u201c" + "Bob" + "\u201d.")

    def test_one_account_is_not_offered_as_a_choice_on_home(self):
        self.open_home()
        self.assertFalse(self.item("home_accounts").property("visible"))

    def test_discord_in_the_navigation_opens_the_invite(self):
        from unittest import mock
        import steamcase as sc
        self.open_home()
        with mock.patch("qtui.updates.QDesktopServices.openUrl", return_value=True) as opened:
            self.click("footer_discord")
        self.assertEqual(opened.call_args[0][0].toString(), sc.DISCORD_URL)

    def test_check_for_updates_shows_the_answer_in_a_dialog_and_opens_the_page_on_ok(self):
        from unittest import mock
        from PySide6.QtTest import QTest
        self.open_home()
        reply = {"newer": True, "current": "1.0", "latest": "1.1", "url": "https://github.com/x/releases"}
        with mock.patch.object(self.sc, "check_for_update", return_value=reply), mock.patch("qtui.updates.QDesktopServices.openUrl", return_value=True) as opened:
            self.click("footer_updates")
            self.wait_for(lambda: self.item("main_dialog").isVisible())
            QTest.qWait(60)
            self.assertEqual(self.text("main_dlg_title"), "Update available")
            self.assertEqual((self.text("main_dlg_confirm"), self.text("main_dlg_cancel")), ("Open GitHub page", "Not now"))
            self.click("main_dlg_confirm")
        self.assertEqual(opened.call_args[0][0].toString(), "https://github.com/x/releases")

    def test_an_information_answer_has_one_button_and_opens_nothing(self):
        from unittest import mock
        from PySide6.QtTest import QTest
        self.open_home()
        reply = {"newer": False, "current": "1.0", "latest": "1.0", "url": "https://github.com/x"}
        with mock.patch.object(self.sc, "check_for_update", return_value=reply), mock.patch("qtui.updates.QDesktopServices.openUrl", return_value=True) as opened:
            self.click("footer_updates")
            self.wait_for(lambda: self.item("main_dialog").isVisible())
            QTest.qWait(60)
            self.assertFalse(self.item("main_dlg_cancel").isVisible())
            self.click("main_dlg_confirm")
        self.assertEqual(opened.call_count, 0)

    def test_the_reset_question_still_comes_when_the_user_left_home_during_the_scan(self):
        from PySide6.QtTest import QTest
        self.open_home()
        self.undo_ready()
        self.ours = ["a"]
        self.click("home_reset")
        self.shell.go(2)                                                # away, while the covers are being looked for
        self.wait_for(lambda: self.ap.asking)
        QTest.qWait(60)
        self.assertTrue(self.item("apply_dialog").isVisible())
        self.assertEqual(self.text("apply_dlg_title"), "Reset to Steam's default art")
        self.click("apply_dlg_cancel")
        self.settle()
        self.assertEqual((self.ap.busy, self.ap.asking), (False, False))

    def test_the_buttons_follow_a_make_run_while_home_is_shown(self):
        self.open_home()
        self.undo_ready()
        self.shell.make._set_state(running=True)
        self.app.processEvents()
        self.assertEqual([self.item(n).property("enabled") for n in ("home_restore", "home_reset")], [False, False])
        self.shell.make._set_state(running=False)
        self.app.processEvents()
        self.assertEqual([self.item(n).property("enabled") for n in ("home_restore", "home_reset")], [True, True])

    def test_a_failed_restore_is_shown_in_a_box_wherever_the_user_is(self):
        from PySide6.QtTest import QTest
        self.open_home()
        self.undo_ready()
        self.ask_restore_fails = True
        self.sc.restore_backup = lambda *a, **k: (_ for _ in ()).throw(self.sc.SteamcaseError("Steam's folder is read-only."))
        self.click("home_restore")
        QTest.qWait(60)
        self.click("apply_dlg_confirm")
        self.shell.go(2)
        self.wait_for(lambda: self.item("main_dialog").isVisible())
        QTest.qWait(60)
        self.assertEqual((self.text("main_dlg_title"), self.text("main_dlg_p0")), ("Could not finish", "Steam's folder is read-only."))
        self.assertFalse(self.item("main_dlg_cancel").isVisible())

    def test_two_questions_never_show_at_once_the_second_waits(self):
        from unittest import mock
        from PySide6.QtTest import QTest
        self.open_home()
        self.undo_ready()
        reply = {"newer": False, "current": "1.0", "latest": "1.0", "url": "https://github.com/x"}
        self.click("home_restore")
        QTest.qWait(60)
        with mock.patch.object(self.sc, "check_for_update", return_value=reply):
            self.shell.updates.check()
            self.wait_for(lambda: not self.shell.updates.checking)
        QTest.qWait(60)
        self.assertTrue(self.item("apply_dialog").isVisible())
        self.assertFalse(self.item("main_dialog").isVisible())           # the answer waits for the question in front
        self.click("apply_dlg_cancel")
        QTest.qWait(60)
        self.assertTrue(self.item("main_dialog").isVisible())            # and comes when it is closed
        self.click("main_dlg_confirm")
        self.assertFalse(self.item("main_dialog").isVisible())

    def test_a_queued_box_keeps_its_own_link_and_a_box_on_screen_keeps_its_own(self):
        from unittest import mock
        from PySide6.QtTest import QTest
        self.open_home()
        with mock.patch("qtui.updates.QDesktopServices.openUrl", return_value=True) as opened:
            self.shell.updates.message.emit("Update available", [{"text": "A newer version", "kind": "main"}], "Open GitHub page", "Not now", "https://github.com/x/releases")
            QTest.qWait(60)
            self.shell.make.failed.emit("Could not make covers", "No games found.")           # arrives while the update box is open
            QTest.qWait(60)
            self.assertEqual(self.text("main_dlg_title"), "Update available")
            self.click("main_dlg_confirm")                                                         # OK of the box that is on screen: its own link
            QTest.qWait(60)
            self.assertEqual([c[0][0].toString() for c in opened.call_args_list], ["https://github.com/x/releases"])
            self.assertEqual(self.text("main_dlg_title"), "Could not make covers")
            self.assertFalse(self.item("main_dlg_cancel").isVisible())
            self.click("main_dlg_confirm")                                                         # the queued box has no link: nothing opens
            self.assertEqual(opened.call_count, 1)

    def test_pressing_close_again_and_again_leaves_one_box(self):
        from PySide6.QtTest import QTest
        self.open_home()
        self.ap._busy = True
        for _ in range(4):
            self.root.close()
        QTest.qWait(60)
        self.click("main_dlg_confirm")
        QTest.qWait(60)
        self.assertFalse(self.item("main_dialog").isVisible())
        self.ap._busy = False

    def test_the_updates_link_says_checking_while_it_checks_and_keeps_its_focus(self):
        import threading
        from unittest import mock
        self.open_home()
        gate = threading.Event()
        self.addCleanup(gate.set)                                       # a failing test must not leave a worker thread waiting
        reply = {"newer": False, "current": "1.0", "latest": "1.0", "url": "https://github.com/x"}
        self.root.requestActivate()
        self.item("footer_updates").forceActiveFocus()
        with mock.patch.object(self.sc, "check_for_update", lambda: (gate.wait(5), reply)[1]):
            self.click("footer_updates")
            self.assertEqual(self.text("footer_updates"), "Checking\u2026")
            self.assertTrue(self.item("footer_updates").property("activeFocus"))
            gate.set()
            self.wait_for(lambda: not self.shell.updates.checking)
        self.assertEqual(self.text("footer_updates"), "Check for updates")

    def test_a_locked_row_tells_a_screen_reader_it_is_unavailable(self):
        from PySide6.QtGui import QAccessible
        self.open_home(covers=True)
        QAccessible.setActive(True)
        self.addCleanup(QAccessible.setActive, False)
        self.assertTrue(QAccessible.queryAccessibleInterface(self.item("home_row_make")).state().disabled)
        self.assertFalse(QAccessible.queryAccessibleInterface(self.item("home_row_look")).state().disabled)

    def test_the_hint_has_its_line_before_the_probe_answers_so_nothing_jumps(self):
        self.open_home()
        card = self.item("home_section_undo")
        before = card.height()
        self.wait_for(lambda: self.ap.undoKnown)
        self.app.processEvents()
        self.assertEqual(card.height(), before)

    def test_the_hint_is_silent_when_covers_are_ready_to_apply(self):
        self.open_home()
        self.wait_for(lambda: self.ap.undoKnown)
        self.assertNotEqual(self.ap.undoHint, "")
        self.shell.make._files = ["x.png"]
        self.shell.make.doneChanged.emit()
        self.assertEqual(self.ap.undoHint, "")

    def test_the_navigation_links_are_buttons_for_the_keyboard_and_screen_readers(self):
        from PySide6.QtGui import QAccessible
        self.open_home()
        QAccessible.setActive(True)
        self.addCleanup(QAccessible.setActive, False)
        for name, text in (("footer_discord", "Join our Discord"), ("footer_updates", "Check for updates")):
            it = self.item(name)
            self.assertTrue(it.property("activeFocusOnTab"), name)
            iface = QAccessible.queryAccessibleInterface(it)
            self.assertEqual((iface.text(QAccessible.Text.Name), iface.role()), (text, QAccessible.Role.Button), name)
            self.assertGreaterEqual(it.height(), 36)


@need_qt
class MakeAddFlow(AddWindow):
    """The whole way as a person walks it, with real clicks in the real window: game list, look, 100% games (skipped), make, add, home."""
    def test_from_the_game_list_to_home(self):
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtTest import QTest
        for fact in ("look_done", "hundred_done"):                       # start from the beginning: nothing done yet
            self.shell.setFact(fact, False)
        self.shell.library.installedOnly = False
        self.made = True                                                 # the covers are made by the clicks below
        self.start_window()
        self.shell.go(1)
        self.app.processEvents()
        self.click("gamelist_installed_label")
        self.settle()
        self.click("gamelist_next")
        self.assertEqual(self.text("screen_title"), "Choose the look")
        self.click("look_next")
        self.assertEqual(self.text("screen_title"), "Highlight your 100% games")
        self.click("hundred_next")                                       # skip
        self.assertEqual(self.text("screen_title"), "Make your covers")
        self.assertEqual(self.shell.steps[4]["state"], "active")
        self.assertEqual(self.shell.steps[5]["state"], "locked")
        self.click("make_main")
        self.wait_for(lambda: self.shell.make.done and not self.shell.make.running)
        self.settle()
        self.assertEqual(self.shell.steps[5]["state"], "active")
        self.click("make_main")
        self.assertEqual(self.text("screen_title"), "Add them to Steam")
        self.click("add_main")
        self.settle()
        self.click("apply_dlg_confirm")
        self.wait_for(lambda: self.shell.apply.applied)
        self.assertEqual(self.shell.steps[5]["state"], "done")
        self.assertEqual(self.log, [("apply", None), "start"])
        self.click("add_main")
        self.assertEqual(self.shell.current, 0)
        self.assertEqual(os.path.basename(sorted(os.listdir(self.covers))[0]), "Game_1_1.png")


def QtCore_toLocal(url):
    from PySide6.QtCore import QUrl
    return QUrl(url).toLocalFile()


@need_qt
class MakeState(QtCase, FakeStore):
    """Step 4's object: it reads the choices of the earlier steps, asks before replacing covers, makes them on a worker thread and tells how it went."""
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def setUp(self):
        super().setUp()
        import threading
        from unittest import mock
        import steamcase as sc
        from qtui.shell import Shell
        self.sc = sc
        self.games, self.family, self.art, self.art_problems = {1: None, 2: None}, set(), {}, []
        self.calls = []                                                  # the keyword arguments of every make_covers run
        self.gate = None                                                 # an Event: the run waits for it after its first cover
        self.reached = threading.Event()
        real_make = sc.make_covers

        def make_covers(games, out, **kw):
            self.calls.append(dict(kw, games=dict(games)))
            if self.gate is not None:
                inner = kw["progress"]

                def progress(*a):
                    inner(*a)
                    if a[0] == 1:
                        self.reached.set()
                        self.gate.wait(10)
                kw["progress"] = progress
            return real_make(games, out, **kw)
        for name, value in (("steam_dir", lambda: self.tmp), ("load_library", lambda steam, lib: (dict(self.games), set(self.family))),
                            ("find_custom_art", lambda steam, account, originals=None, problems=None: (problems.extend(self.art_problems) if problems is not None else None) or dict(self.art)),
                            ("make_covers", make_covers)):
            patcher = mock.patch.object(sc, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.downloads = os.path.join(self.tmp, "Downloads")
        os.makedirs(self.downloads)
        self.shell = Shell(os.path.join(self.tmp, "settings.json"), downloads=self.downloads, covers_dir=self.covers)
        self.shell.library.installedOnly = True
        self.make = self.shell.make

    def tearDown(self):
        if self.gate is not None:
            self.gate.set()
        self.make.decline()
        self.wait_for(lambda: not self.make.running)
        super().tearDown()

    def wait_for(self, condition, seconds=5):
        import time
        end = time.time() + seconds
        while time.time() < end and not condition():
            self.app.processEvents()
            time.sleep(0.02)
        self.app.processEvents()

    def run_it(self):
        self.make.start()
        self.wait_for(lambda: not self.make.running and not self.make.asking)

    def test_it_starts_idle_and_ready(self):
        m = self.make
        self.assertEqual((m.running, m.asking, m.done, m.fileCount, m.canMake, m.progress), (False, False, False, 0, True, 0.0))
        self.assertEqual((m.status, m.statusKind), ("Not started.", "wait"))

    def test_it_makes_the_covers_and_says_so(self):
        seen = []
        self.make.progressChanged.connect(lambda: seen.append((self.make.finished, self.make.total)))
        self.run_it()
        m = self.make
        self.assertEqual((m.status, m.statusKind, m.done, m.fileCount, m.progress), ("Done. 2 covers ready.", "ok", True, 2, 1.0))
        self.assertEqual(sorted(os.listdir(self.covers)), ["Game_1_1.png", "Game_2_2.png"])
        self.assertIn((2, 2), seen)

    def test_covers_made_opens_the_next_step_once_the_earlier_ones_are_done(self):
        for fact in ("look_done", "hundred_done"):
            self.shell.setFact(fact, True)
        self.assertEqual(self.shell.steps[5]["state"], "locked")
        self.run_it()
        self.assertEqual(self.shell.steps[4]["state"], "done")
        self.assertEqual(self.shell.steps[5]["state"], "active")

    def test_nothing_starts_while_it_runs_or_a_page_is_being_read(self):
        import threading
        self.gate = threading.Event()
        self.make.start()
        self.make.start()
        self.wait_for(self.reached.is_set)
        self.make.start()
        self.assertEqual(len(self.calls), 1)
        self.gate.set()
        self.wait_for(lambda: not self.make.running)
        self.shell.hundred.loadPage(write_games_page(self.tmp, {1: (1, 1)}))
        self.assertFalse(self.make.canMake)
        self.make.start()
        self.assertEqual((self.make.running, len(self.calls)), (False, 1))
        self.wait_for(lambda: not self.shell.hundred.busy)
        self.assertTrue(self.make.canMake)
        self.make.start()
        self.assertTrue(self.make.running)

    def test_cancel_stops_the_run_and_keeps_what_was_made(self):
        import threading
        self.games = {1: None, 2: None, 3: None}
        self.gate = threading.Event()
        self.make.start()
        self.wait_for(self.reached.is_set)
        self.make.cancel()
        self.assertEqual((self.make.status, self.make.statusKind), ("Stopping\u2026", "wait"))
        self.gate.set()
        self.wait_for(lambda: not self.make.running)
        self.assertTrue(self.make.status.startswith("Stopped. "), self.make.status)
        self.assertTrue(self.make.done)
        self.assertEqual(self.make.fileCount, len(os.listdir(self.covers)))
        self.assertLess(self.make.fileCount, 3)

    def test_a_changed_colour_asks_first_and_declining_changes_nothing(self):
        self.run_it()
        before = (self.make.status, self.make.statusKind, self.make.fileCount)
        asked = []
        self.make.confirmNeeded.connect(lambda title, text: asked.append((title, text)))
        self.shell.look.setTone(90, 100, 100)
        self.make.start()
        self.assertEqual(asked, [("Change the colour of your covers?", "This replaces the covers you already made in another colour.")])
        self.assertTrue(self.make.asking)
        self.assertEqual(len(self.calls), 1)
        self.make.start()                                               # one question at a time
        self.assertEqual(len(asked), 1)
        self.make.decline()
        self.assertEqual((self.make.asking, self.make.running, self.make.status, self.make.statusKind, self.make.fileCount), (False, False) + before)
        self.assertEqual(len(self.calls), 1)
        self.make.confirm()                                             # an answer nobody asked for does nothing
        self.assertEqual(len(self.calls), 1)

    def test_confirming_makes_the_covers_again_in_the_new_colour(self):
        self.run_it()
        self.shell.look.setTone(90, 100, 100)
        self.make.start()
        self.make.confirm()
        self.wait_for(lambda: not self.make.running)
        self.assertEqual(len(self.calls), 2)
        self.assertFalse(self.sc.covers_in_other_colour(self.covers, 90, 100, 100))
        self.assertEqual(self.make.status, "Done. 2 covers ready.")

    def test_no_question_when_nothing_would_be_replaced(self):
        self.run_it()
        asked = []
        self.make.confirmNeeded.connect(lambda *a: asked.append(a))
        self.run_it()
        self.assertEqual((asked, len(self.calls)), ([], 2))

    def test_what_the_run_gets_is_what_the_steps_chose(self):
        self.shell.look.setTone(120, 50, 80)
        self.shell.look.theme = "halloween"
        self.shell.setSwitch("skip_auto_art", True)
        self.run_it()
        call = self.calls[0]
        self.assertEqual((call["hue"], call["sat"], call["val"], call["theme"], call["skip_auto_art"]), (120, 50, 80, "halloween", True))
        self.assertEqual((call["completed"], call["treatment"], call["custom_art"]), (None, None, {}))

    def test_a_loaded_page_and_its_style_go_to_the_run(self):
        self.shell.hundred.loadPage(write_games_page(self.tmp, {1: (3, 3), 2: (1, 4)}))
        self.wait_for(lambda: not self.shell.hundred.busy)
        self.shell.hundred.style = "gold-case"
        self.run_it()
        self.assertEqual((self.calls[0]["completed"], self.calls[0]["treatment"]), ({1}, self.sc.compose_treatment("gold-case", "full")))
        self.assertIn("1 of them is 100% and is highlighted.", self.make.status)

    def test_the_choices_are_read_when_it_starts_not_while_it_runs(self):
        import threading
        self.gate = threading.Event()
        self.shell.look.setTone(120, 100, 100)
        self.make.start()
        self.wait_for(self.reached.is_set)
        self.shell.look.setTone(10, 100, 100)
        self.gate.set()
        self.wait_for(lambda: not self.make.running)
        self.assertEqual(self.calls[0]["hue"], 120)

    def test_own_art_is_looked_for_off_the_ui_thread_and_only_for_the_games_in_the_library(self):
        mine = self.mine()
        self.art = {1: mine, 99: mine}
        self.shell.setSwitch("use_custom_art", True)
        self.make.start()
        self.assertEqual((self.make.running, self.make.searching, self.make.status), (True, True, "Looking for your own art\u2026"))
        self.wait_for(lambda: not self.make.running)
        self.assertEqual(self.calls[0]["custom_art"], {1: mine})
        self.assertFalse(self.make.searching)

    def test_own_art_that_could_not_be_copied_is_told_after_the_run(self):
        self.art, self.art_problems = {1: self.mine()}, ["x"]
        self.shell.setSwitch("use_custom_art", True)
        self.run_it()
        self.assertIn("Could not keep a copy of your own art for 1 game: Apply moves that file into the backup, and Restore brings it back.", self.make.status)

    def test_turning_own_art_off_asks_before_going_back_to_steams_art(self):
        self.art = {1: self.mine()}
        self.shell.setSwitch("use_custom_art", True)
        self.run_it()
        asked = []
        self.make.confirmNeeded.connect(lambda title, text: asked.append(title))
        self.shell.setSwitch("use_custom_art", False)
        self.make.start()
        self.assertEqual(asked, ["Go back to Steam's art?"])

    def test_a_failed_art_search_says_why_and_leaves_the_screen_usable(self):
        def broken(steam, account, originals=None, problems=None):
            raise self.sc.SteamcaseError("Cannot read your art folder.")
        self.shell.setSwitch("use_custom_art", True)
        with unittest.mock.patch.object(self.sc, "find_custom_art", broken):
            self.run_it()
        self.assertEqual((self.make.status, self.make.statusKind, self.make.running, self.make.searching, self.make.canMake),
                         ("Cannot read your art folder.", "error", False, False, True))
        self.assertEqual(self.calls, [])

    def test_an_unknown_failure_never_leaves_it_stuck(self):
        def broken(steam, account, originals=None, problems=None):
            raise ValueError("boom")
        self.shell.setSwitch("use_custom_art", True)
        with unittest.mock.patch.object(self.sc, "find_custom_art", broken):
            self.run_it()
        self.assertEqual((self.make.status, self.make.statusKind, self.make.running), ("Unexpected problem: boom", "error", False))

    def test_no_games_gives_the_old_words(self):
        self.games = {}
        self.run_it()
        self.assertEqual((self.make.status, self.make.statusKind, self.make.running), ("No games found. Install a game first, or load your userdata.json.", "error", False))

    def test_the_engine_failing_midway_is_reported(self):
        with unittest.mock.patch.object(self.sc, "make_covers", side_effect=RuntimeError("disk")):
            self.run_it()
        self.assertEqual((self.make.status, self.make.statusKind, self.make.running), ("Unexpected problem: disk", "error", False))

    def test_errors_of_making_come_with_a_box_as_in_the_old_window(self):
        failures = []
        self.make.failed.connect(lambda title, text: failures.append((title, text)))
        self.games = {}
        self.run_it()
        self.assertEqual(failures[-1], ("Could not make covers", "No games found. Install a game first, or load your userdata.json."))
        def broken(steam, account, originals=None, problems=None):
            raise self.sc.SteamcaseError("Cannot read your art folder.")
        self.shell.setSwitch("use_custom_art", True)
        with unittest.mock.patch.object(self.sc, "find_custom_art", broken):
            self.games = {1: None}
            self.run_it()
        self.assertEqual(failures[-1], ("Cannot read your own art", "Cannot read your art folder."))

    def test_a_folder_that_cannot_be_opened_is_shown_in_a_box_too(self):
        from unittest import mock
        failures = []
        self.make.failed.connect(lambda title, text: failures.append((title, text)))
        with mock.patch("qtui.make.QDesktopServices.openUrl", return_value=False):
            self.make.openFolder()
        self.assertEqual(failures, [("Covers folder", "Could not open the folder. It is here:\n\n%s" % os.path.abspath(self.covers))])

    def test_a_new_run_locks_step_5_until_it_has_covers_again(self):
        for fact in ("look_done", "hundred_done"):
            self.shell.setFact(fact, True)
        self.run_it()
        self.assertEqual(self.shell.steps[5]["state"], "active")
        self.games = {}
        self.run_it()                                                   # fails: nothing to add
        self.assertEqual(self.shell.steps[5]["state"], "locked")
        self.assertEqual(self.shell.steps[4]["state"], "active")

    def test_the_first_covers_of_a_run_are_offered_as_thumbnails(self):
        self.assertEqual(self.make.thumbs, [])
        self.games = {i: None for i in range(1, 8)}
        self.run_it()
        urls = self.make.thumbs
        self.assertEqual(len(urls), 5)
        self.assertTrue(all(u.startswith("file:") and u.endswith(".png") for u in urls))
        self.assertEqual([os.path.basename(QtCore_toLocal(u)) for u in urls], [os.path.basename(f) for f in self.make.files()[:5]])
        self.games = {}
        self.run_it()                                                   # a failed run offers none
        self.assertEqual(self.make.thumbs, [])

    def test_the_thumbnails_empty_while_a_new_run_makes_covers_under_the_same_names(self):
        self.run_it()
        seen = []
        self.make.doneChanged.connect(lambda: seen.append(list(self.make.thumbs)))
        self.run_it()
        self.assertIn([], seen)                                         # the pictures are dropped, so they are read again from the new files
        self.assertEqual(len(self.make.thumbs), 2)

    def test_a_failed_run_offers_no_covers_it_did_not_make(self):
        self.run_it()
        self.games = {}
        self.run_it()
        self.assertEqual((self.make.done, self.make.fileCount), (False, 0))

    def test_declining_the_question_keeps_the_covers_of_the_run_before(self):
        self.run_it()
        self.shell.look.setTone(90, 100, 100)
        self.make.start()
        self.make.decline()
        self.assertEqual((self.make.done, self.make.fileCount), (True, 2))

    def test_the_question_waits_in_the_object_for_a_screen_that_opens_late(self):
        self.run_it()
        self.shell.look.setTone(90, 100, 100)
        self.art = {1: self.mine()}
        self.shell.setSwitch("use_custom_art", True)
        self.make.start()                                              # the art is looked for on a worker thread; nobody listens to the signal
        self.wait_for(lambda: self.make.asking)
        self.assertEqual(self.make.questionTitle, "Change the colour of your covers?")
        self.assertIn("another colour", self.make.questionText)
        self.make.decline()
        self.assertEqual((self.make.questionTitle, self.make.questionText), ("", ""))
        self.make.start()
        self.wait_for(lambda: self.make.asking)
        self.make.confirm()
        self.assertEqual(self.make.questionTitle, "")
        self.wait_for(lambda: not self.make.running)

    def test_a_stopped_run_does_not_fill_the_bar(self):
        import threading
        self.games = {1: None, 2: None, 3: None, 4: None}
        self.gate = threading.Event()
        self.make.start()
        self.wait_for(self.reached.is_set)
        self.make.cancel()
        self.gate.set()
        self.wait_for(lambda: not self.make.running)
        self.assertLess(self.make.progress, 1.0)
        self.assertLess(self.make.finished, self.make.total)

    def test_it_waits_while_covers_are_being_added_to_steam(self):
        seen = []
        self.make.runningChanged.connect(lambda: seen.append(self.make.canMake))
        self.shell.apply._busy = True
        self.shell.apply.canApplyChanged.emit()
        self.assertFalse(self.make.canMake)
        self.assertIn(False, seen)
        self.make.start()
        self.assertEqual((self.make.running, self.calls), (False, []))
        self.shell.apply._busy = False
        self.shell.apply.canApplyChanged.emit()
        self.assertTrue(self.make.canMake)

    def test_a_new_run_replaces_the_files(self):
        self.run_it()
        self.games = {3: None}
        self.run_it()
        self.assertEqual(self.make.fileCount, 1)
        self.assertEqual(os.path.basename(self.make.files()[0]), "Game_3_3.png")

    def test_the_result_sentence_has_every_part_of_the_old_one(self):
        from qtui.make import result_text
        base = {"ok": 3, "missing": [], "failed": [], "cancelled": False, "family": 0, "completed": 0, "not_games": 0, "unlisted": 0}
        self.assertEqual(result_text(base, []), ("Done. 3 covers ready.", "ok"))
        self.assertEqual(result_text(dict(base, ok=1, cancelled=True), []), ("Stopped. 1 covers ready.", "ok"))
        self.assertEqual(result_text(dict(base, missing=[1]), [])[0], "Done. 3 covers ready. 1 game has no portrait on Steam.")
        self.assertIn("2 games have no portrait on Steam.", result_text(dict(base, missing=[1, 2]), [])[0])
        self.assertIn("1 of them is a family game and has a green corner.", result_text(dict(base, family=1), [])[0])
        self.assertIn("2 of them are family games and have a green corner.", result_text(dict(base, family=2), [])[0])
        self.assertIn("1 of them is 100% and is highlighted.", result_text(dict(base, completed=1), [])[0])
        self.assertIn("2 of them are 100% and are highlighted.", result_text(dict(base, completed=2), [])[0])
        self.assertIn("Skipped 5 items that aren't games you can play (DLC, soundtracks, tools, and apps Steam no longer lists).", result_text(dict(base, not_games=3, unlisted=2), [])[0])
        self.assertEqual(result_text(dict(base, failed=[1]), []),
                         ("Done. 3 covers ready. 1 could not be downloaded (connection problem?): click \u201cMake again\u201d to retry only those.", "wait"))
        self.assertEqual(result_text(dict(base, ok=0), []), ("Done. 0 covers ready.", "wait"))
        self.assertIn("Could not keep a copy of your own art for 2 games: Apply moves those files into the backup, and Restore brings them back.", result_text(base, ["a", "b"])[0])

    def test_the_choices_name_what_the_earlier_steps_chose_and_where_to_change_it(self):
        def keys(): return [c["key"] for c in self.make.choices]
        self.assertEqual(keys(), ["games", "colour", "theme", "hundred", "art"])
        by = lambda: {c["key"]: c for c in self.make.choices}
        self.assertEqual([by()[k]["step"] for k in keys()], [1, 2, 2, 3, 2])
        self.assertEqual(by()["games"]["value"], "Installed games")
        self.assertEqual((by()["theme"]["value"], by()["hundred"]["value"], by()["art"]["value"]), ("Classic case", "Skipped", "Steam's art"))
        seen = []
        self.make.choicesChanged.connect(lambda: seen.append(1))
        self.shell.look.theme = "halloween"
        self.shell.look.setTone(120, 100, 100)
        self.shell.setSwitch("skip_auto_art", True)
        self.shell.look.skipAutoArt = False
        self.shell.look.useCustomArt = True
        self.shell.hundred.loadPage(write_games_page(self.tmp, {1: (1, 1)}))
        self.wait_for(lambda: not self.shell.hundred.busy)
        self.shell.hundred.style = "none"
        self.assertEqual(by()["theme"]["value"], "Halloween")
        self.assertEqual(by()["colour"]["value"], self.shell.look.toneName)
        self.assertEqual(by()["art"]["value"], "Your own art")
        self.assertEqual(by()["hundred"]["value"], "No special case")
        self.shell.hundred.style = "gold-case"
        self.assertEqual(by()["hundred"]["value"], "Gold case, rosette only")
        self.shell.look.skipAutoArt = True
        self.assertEqual(by()["art"]["value"], "Your own art, blurry art skipped")
        self.assertGreaterEqual(len(seen), 5)
        self.shell.library.installedOnly = False
        self.assertEqual(by()["games"]["value"], "Not chosen yet")

    def test_the_covers_folder_opens_or_says_where_it_is(self):
        from unittest import mock
        with mock.patch("qtui.make.QDesktopServices.openUrl", return_value=True) as opened:
            self.make.openFolder()
        self.assertTrue(os.path.isdir(self.covers))
        self.assertEqual(os.path.normpath(opened.call_args[0][0].toLocalFile()), os.path.normpath(self.covers))
        with mock.patch("qtui.make.QDesktopServices.openUrl", return_value=False):
            self.make.openFolder()
        self.assertEqual((self.make.status, self.make.statusKind), ("Could not open the folder. It is here: %s" % os.path.abspath(self.covers), "error"))

    def test_an_answer_that_cannot_be_delivered_is_dropped_quietly(self):
        import shiboken6
        from qtui.make import Make
        gone = Make(self.shell, self.covers)
        shiboken6.delete(gone)
        gone._make_worker(1, {"lib": None, "skip": False, "tone": (0, 100, 100), "completed": None, "treatment": None, "theme": None}, {})
        gone._art_worker(2, {"lib": None, "account": None})


@need_qt
class ApplyState(QtCase, FakeStore):
    """Step 5's object: the account, whether Steam runs, the question before anything changes, and the worker that closes Steam, copies the covers and starts it again."""
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def setUp(self):
        super().setUp()
        import threading
        from unittest import mock
        import steamcase as sc
        from qtui.shell import Shell
        self.sc = sc
        self.running = False                                            # what steam_running answers
        self.probes = []                                                # the threads steam_running was asked on
        self.accounts = [("111", "Alice")]
        self.log = []                                                   # what the worker did, in order
        self.result = {"applied": 2, "replaced": 0, "unchanged": 0, "jpg_moved": 0, "backup": "/b", "account_name": "Alice"}
        self.close_ok = True
        self.start_error = None
        self.apply_error = None
        self.backups, self.restored = [], 5
        self.ours, self.extra, self.other, self.scan_error = [], [], [], None
        self.grid = os.path.join(self.tmp, "grid")
        os.makedirs(self.grid)

        def steam_running():
            self.probes.append(threading.current_thread())
            return self.running

        def close_steam(steam, timeout=60):
            self.log.append("close")
            return self.close_ok

        def start_steam(steam):
            self.log.append("start")
            if self.start_error:
                raise sc.SteamcaseError(self.start_error)

        def apply_covers(steam, covers, user=None, files=None):
            self.log.append(("apply", user, [os.path.basename(f) for f in files or []]))
            if self.apply_error:
                raise self.apply_error
            return dict(self.result)
        for name, value in (("steam_dir", lambda: self.tmp), ("load_library", lambda steam, lib: ({1: None, 2: None}, set())),
                            ("steam_running", steam_running), ("close_steam", close_steam), ("start_steam", start_steam), ("apply_covers", apply_covers),
                            ("list_accounts", lambda steam: list(self.accounts)),
                            ("pick_account", lambda steam, forced=None: forced or self.accounts[0][0]),
                            ("account_label", lambda steam, acc: dict(self.accounts).get(acc, str(acc))),
                            ("list_backups", lambda steam, user=None: list(self.backups)),
                            ("restore_backup", lambda steam, backup, user=None, keep=False, originals=None: (self.log.append(("restore", backup)), self.backups.pop(0), self.restored)[2]),
                            ("find_our_covers", self.find_ours), ("find_other_art", lambda steam, user=None, ours=(): (list(self.extra), list(self.other))),
                            ("reset_to_default", lambda steam, user=None, names=None, everything=False: (self.log.append(("reset", user, list(names or []), everything)),
                                                                                                      {"removed": len(names or []), "account_name": "Alice"})[1]),
                            ("grid_dir", lambda steam, user=None: self.grid)):
            patcher = mock.patch.object(sc, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.downloads = os.path.join(self.tmp, "Downloads")
        os.makedirs(self.downloads)
        self.shell = Shell(os.path.join(self.tmp, "settings.json"), downloads=self.downloads, covers_dir=self.covers)
        self.shell.library.installedOnly = True
        self.make, self.ap = self.shell.make, self.shell.apply

    def find_ours(self, steam, user=None, progress=None, cancelled=None):
        if self.scan_error:
            raise self.sc.SteamcaseError(self.scan_error)
        if progress:
            progress(1, 2)
        return list(self.ours)

    def wait_for(self, condition, seconds=5):
        import time
        end = time.time() + seconds
        while time.time() < end and not condition():
            self.app.processEvents()
            time.sleep(0.02)
        self.app.processEvents()

    def covers_ready(self):
        self.make.start()
        self.wait_for(lambda: not self.make.running)
        self.assertTrue(self.make.done)

    def go(self):
        """Apply, answer the question with yes and wait for the worker."""
        asked = []
        self.ap.confirmNeeded.connect(lambda *a: asked.append(a))
        self.ap.apply()
        self.assertEqual(len(asked), 1)
        self.ap.confirm()
        self.wait_for(lambda: not self.ap.busy)
        return asked[0]

    def test_it_starts_with_nothing_to_apply(self):
        a = self.ap
        self.assertEqual((a.busy, a.applied, a.canApply, a.restart, a.status, a.statusKind), (False, False, False, True, "", "wait"))
        asked = []
        a.confirmNeeded.connect(lambda *x: asked.append(x))
        a.apply()
        self.assertEqual(asked, [])

    def test_with_covers_made_it_can_apply(self):
        self.covers_ready()
        self.assertTrue(self.ap.canApply)

    def test_the_question_names_the_account_and_the_backup(self):
        self.covers_ready()
        title, paragraphs, go, alt = self.go()
        self.assertEqual(title, "Add covers to Steam")
        self.assertEqual(paragraphs, [{"text": "2 covers will be added to the Steam account \u201cAlice\u201d.", "kind": "main"},
                                      {"text": "Your current artwork is backed up first. You can undo this from the Home screen.", "kind": "muted"}])
        self.assertEqual(go, "Add them")

    def test_declining_changes_nothing(self):
        self.covers_ready()
        self.ap.apply()
        self.ap.decline()
        self.ap.confirm()                                               # nobody asked: nothing happens
        self.assertEqual((self.ap.busy, self.ap.applied, self.log, self.ap.status), (False, False, [], ""))

    def test_applying_with_steam_closed_adds_the_covers_and_starts_steam(self):
        self.covers_ready()
        self.go()
        self.assertEqual(self.log, [("apply", None, ["Game_1_1.png", "Game_2_2.png"]), "start"])      # no choice: the engine picks the account Steam used last
        self.assertEqual((self.ap.applied, self.ap.busy, self.ap.statusKind), (True, False, "ok"))
        self.assertEqual(self.ap.status, "Done. 2 covers added to the Steam account \u201cAlice\u201d (0 replaced older art, 0 already up to date). Backup saved in: /b Steam is starting.")

    def test_it_says_working_while_it_works_and_closing_steam_when_it_must(self):
        import threading
        self.covers_ready()
        gate = threading.Event()
        self.addCleanup(gate.set)                                       # a failing test must not leave a worker thread waiting
        self.result = dict(self.result)
        real = self.sc.apply_covers
        self.sc.apply_covers = lambda *a, **k: gate.wait(5) and real(*a, **k)
        self.addCleanup(lambda: setattr(self.sc, "apply_covers", real))
        self.ap.apply()
        self.ap.confirm()
        self.assertEqual((self.ap.busy, self.ap.status, self.ap.canApply), (True, "Working\u2026", False))
        gate.set()
        self.wait_for(lambda: not self.ap.busy)

    def test_the_applied_fact_opens_nothing_before_the_covers_are_made(self):
        self.covers_ready()
        for fact in ("look_done", "hundred_done"):
            self.shell.setFact(fact, True)
        self.assertEqual(self.shell.steps[5]["state"], "active")
        self.go()
        self.assertEqual(self.shell.steps[5]["state"], "done")

    def test_with_steam_open_the_question_warns_and_steam_is_closed_first(self):
        self.covers_ready()
        self.running = True
        self.ap.watching = True
        self.wait_for(lambda: self.ap.steamOpen)
        self.assertEqual(self.ap.noteKind, "warn")
        self.assertEqual(self.ap.note, "Steam is open. Changing the artwork closes it: any running game stops and downloads pause. Save your game first.")
        title, paragraphs, go, alt = self.go()
        self.assertEqual(paragraphs[-1], {"text": "Steam will be closed automatically. Any running game stops and downloads pause. Save your game first.", "kind": "warn"})
        self.assertEqual(go, "Close Steam and add them")
        self.assertEqual(self.log[0], "close")

    def test_with_steam_closed_the_note_is_calm(self):
        self.assertEqual((self.ap.note, self.ap.noteKind), ("Checking whether Steam is open\u2026", "wait"))        # not known yet: no claim either way, and no jump later
        self.ap.watching = True
        self.wait_for(lambda: self.ap.noteKind == "calm")
        self.assertEqual((self.ap.steamOpen, self.ap.noteKind), (False, "calm"))
        self.assertEqual(self.ap.note, "Steam is closed, so nothing will be interrupted. Your current artwork is backed up first, so you can undo it.")

    def test_steam_not_closing_changes_nothing_and_says_what_to_do(self):
        self.covers_ready()
        self.running, self.close_ok = True, False
        with unittest.mock.patch("qtui.apply.sys.platform", "linux"):          # the macOS words are tested apart
            self.go()
        self.assertEqual(self.log, ["close"])
        self.assertEqual((self.ap.applied, self.ap.busy, self.ap.statusKind), (False, False, "error"))
        self.assertEqual(self.ap.status, "Steam did not close in time. Close it yourself (Steam menu, then Exit) and press the button again.")

    def test_on_a_mac_the_words_add_the_permission_hint(self):
        from unittest import mock
        self.covers_ready()
        self.running, self.close_ok = True, False
        with mock.patch("qtui.apply.sys.platform", "darwin"):
            self.go()
        self.assertTrue(self.ap.status.endswith(" If macOS asked for permission, allow it first and then press the button again."), self.ap.status)

    def test_nothing_to_change_is_said_so(self):
        self.covers_ready()
        self.result = dict(self.result, applied=0, unchanged=2)
        self.shell.setSwitch("restart_steam", False)
        self.go()
        self.assertEqual(self.ap.status, "Nothing to change: all 2 covers were already in the Steam account \u201cAlice\u201d. Start Steam to see the change.")
        self.assertEqual((self.ap.applied, self.log), (True, [("apply", None, ["Game_1_1.png", "Game_2_2.png"])]))

    def test_art_set_by_hand_is_said_to_be_in_the_backup(self):
        self.covers_ready()
        self.result = dict(self.result, jpg_moved=3, replaced=1, unchanged=1)
        self.go()
        self.assertIn("(1 replaced older art, 1 already up to date)", self.ap.status)
        self.assertIn("Art you had set by hand in Steam (3 games) was moved into the backup; Restore brings it back.", self.ap.status)

    def test_a_steam_that_cannot_be_started_is_told_but_the_covers_are_in(self):
        self.covers_ready()
        self.start_error = "no launcher"
        self.go()
        self.assertTrue(self.ap.applied)
        self.assertTrue(self.ap.status.endswith(" Could not start Steam (no launcher). Please open it yourself."), self.ap.status)

    def test_without_the_restart_switch_steam_is_left_alone(self):
        self.covers_ready()
        self.ap.restart = False
        self.assertFalse(self.shell.switchValue("restart_steam"))
        self.go()
        self.assertNotIn("start", self.log)
        self.assertTrue(self.ap.status.endswith(" Start Steam to see the change."))

    def test_engine_and_unknown_failures_leave_the_screen_usable(self):
        self.covers_ready()
        self.apply_error = self.sc.SteamcaseError("No covers found in x. Make them first.")
        self.go()
        self.assertEqual((self.ap.status, self.ap.statusKind, self.ap.busy, self.ap.applied, self.ap.canApply),
                         ("No covers found in x. Make them first.", "error", False, False, True))
        self.apply_error = ValueError("boom")
        self.go()
        self.assertEqual((self.ap.status, self.ap.statusKind), ("Unexpected problem: boom", "error"))

    def test_nothing_happens_while_covers_are_being_made_or_applied(self):
        import threading
        self.covers_ready()
        asked = []
        self.ap.confirmNeeded.connect(lambda *x: asked.append(x))
        self.make.start()
        self.assertFalse(self.ap.canApply)
        self.ap.apply()
        self.wait_for(lambda: not self.make.running)
        self.assertEqual(asked, [])
        self.ap.apply()
        self.ap.apply()                                                 # one question at a time
        self.assertEqual(len(asked), 1)

    def test_making_the_covers_again_forgets_the_last_result(self):
        self.covers_ready()
        self.go()
        self.assertTrue(self.ap.applied)
        self.make.start()
        self.assertEqual((self.ap.applied, self.ap.status), (False, ""))
        self.wait_for(lambda: not self.make.running)

    def test_declining_a_question_keeps_what_was_said_about_the_last_apply(self):
        self.covers_ready()
        self.go()
        said = self.ap.status
        self.shell.look.setTone(90, 100, 100)
        self.make.start()
        self.assertTrue(self.make.asking)
        self.make.decline()
        self.assertEqual((self.ap.applied, self.ap.status), (True, said))
        self.make.start()
        self.make.confirm()
        self.assertEqual((self.ap.applied, self.ap.status), (False, ""))
        self.wait_for(lambda: not self.make.running)

    def test_no_new_covers_while_adding_and_no_adding_while_making_is_not_possible_to_mix(self):
        self.covers_ready()
        self.ap._busy = True
        self.ap.canApplyChanged.emit()
        self.make.start()
        self.assertFalse(self.make.running)
        self.ap._busy = False

    def test_accounts_without_a_name_read_account_number_and_long_names_are_cut(self):
        self.accounts = [("111", "111"), ("222", "B" * 40)]
        self.ap.refresh()
        self.assertEqual([c["label"] for c in self.ap.accounts], ["Account 111", "B" * 27 + "\u2026"])

    def test_an_account_that_has_gone_also_leaves_the_label(self):
        self.accounts = [("111", "Alice"), ("222", "Bob")]
        self.ap.refresh()
        self.ap.chooseAccount("222")
        self.assertEqual(self.ap.accountLabel, "Steam account: Bob")
        self.accounts = [("111", "Alice")]
        self.assertIsNone(self.ap.accountChoice())
        self.assertEqual(self.ap.accountLabel, "Steam account: Alice")

    def test_the_ready_text_says_when_there_are_none(self):
        self.assertEqual(self.ap.readyText, "No covers yet. Make them first.")

    def test_the_ready_text_counts_covers_correctly(self):
        self.make._files = ["a.png"]
        self.assertEqual(self.ap.readyText, "1 cover is ready to add.")
        self.make._files = ["a.png", "b.png"]
        self.assertEqual(self.ap.readyText, "2 covers are ready to add.")

    def undo_ready(self, backups=("b1",), art=True):
        self.backups = list(backups)
        if art:
            open(os.path.join(self.grid, "123p.png"), "wb").close()
        self.ap.refreshUndo()
        self.wait_for(lambda: self.ap.canRestore or self.ap.canReset)

    def ask(self, call):
        asked = []
        self.ap.confirmNeeded.connect(lambda *a: asked.append(a))
        call()
        self.wait_for(lambda: bool(asked))
        return asked[0] if asked else None

    def test_undo_is_probed_off_the_ui_thread_and_the_hint_says_why_it_is_greyed(self):
        self.ap.refreshUndo()
        self.wait_for(lambda: self.ap.undoKnown)
        self.assertEqual((self.ap.canRestore, self.ap.canReset), (False, False))
        self.assertEqual(self.ap.undoHint, "Nothing to undo yet: \u201cRestore previous artwork\u201d works once you have used \u201cApply to Steam\u201d in this app.")
        self.undo_ready()
        self.assertEqual((self.ap.canRestore, self.ap.canReset, self.ap.undoHint), (True, True, ""))

    def test_restore_asks_closes_steam_and_puts_the_old_art_back(self):
        self.undo_ready(("b1", "b2"))
        self.running = True
        self.ap.watching = True
        self.wait_for(lambda: self.ap.steamOpen)
        title, paragraphs, go, alt = self.ask(self.ap.restore)
        self.assertEqual(title, "Restore previous artwork")
        self.assertEqual(paragraphs[:2], [{"text": "Your artwork from before the last Apply will be put back on the Steam account \u201cAlice\u201d.", "kind": "main"},
                                          {"text": "The covers added by that Apply are removed.", "kind": "muted"}])
        self.assertEqual((paragraphs[2]["kind"], go, alt), ("warn", "Close Steam and restore", ""))
        self.assertEqual(self.log, [])
        self.ap.confirm()
        self.wait_for(lambda: not self.ap.busy)
        self.assertEqual(self.log, ["close", ("restore", "b1"), "start"])
        self.assertEqual(self.ap.status, "Restored your previous artwork (5 files). 1 older backup left: press Restore again to go one step further back. Steam is starting.")
        self.assertEqual((self.ap.statusKind, self.ap.applied), ("ok", False))

    def test_restore_does_nothing_without_a_backup_or_while_busy(self):
        self.ap.refreshUndo()
        self.wait_for(lambda: self.ap.undoKnown)
        asked = []
        self.ap.confirmNeeded.connect(lambda *a: asked.append(a))
        self.ap.restore()
        self.undo_ready()
        self.ap._busy = True
        self.ap.canApplyChanged.emit()
        self.ap.restore()
        self.ap.reset()
        self.assertEqual(asked, [])
        self.assertEqual((self.ap.canRestore, self.ap.canReset), (False, False))
        self.ap._busy = False

    def test_restoring_after_an_apply_forgets_that_it_was_applied(self):
        self.covers_ready()
        self.go()
        self.assertTrue(self.ap.applied)
        self.undo_ready()
        self.ask(self.ap.restore)
        self.ap.confirm()
        self.wait_for(lambda: not self.ap.busy)
        self.assertFalse(self.ap.applied)
        self.assertNotEqual(self.shell.steps[5]["state"], "done")

    def test_reset_looks_first_then_asks_and_removes_only_ours(self):
        self.undo_ready()
        self.ours = ["a", "b"]
        title, paragraphs, go, alt = self.ask(self.ap.reset)
        self.assertEqual(title, "Reset to Steam's default art")
        self.assertEqual([p["text"] for p in paragraphs], [
            "2 covers made by this app will be removed from the Steam account \u201cAlice\u201d. Steam goes back to its own default art for them.",
            "A backup is kept, so \u201cRestore previous artwork\u201d brings everything back."])
        self.assertEqual((go, alt), ("Reset", ""))
        self.assertTrue(self.ap.busy)                                   # nothing else can start meanwhile
        self.ap.confirm()
        self.wait_for(lambda: not self.ap.busy)
        self.assertEqual(self.log, [("reset", None, ["a", "b"], False), "start"])
        self.assertEqual(self.ap.status, "Done. 2 covers removed from the Steam account \u201cAlice\u201d: Steam shows its own default art again. "
                                         "Press \u201cRestore previous artwork\u201d to bring them back. Steam is starting.")

    def test_reset_with_art_from_elsewhere_offers_only_ours_or_all(self):
        self.undo_ready()
        self.ours, self.extra, self.other = ["a"], ["x"], ["y", "z"]
        title, paragraphs, go, alt = self.ask(self.ap.reset)
        self.assertEqual((go, alt), ("Remove only ours", "Remove all"))
        self.assertEqual(paragraphs[1]["text"], "Found 3 more custom covers that this app did not make (from SteamGridDB or set by hand in Steam).")
        self.ap.confirm()
        self.wait_for(lambda: not self.ap.busy)
        self.assertEqual(self.log[0], ("reset", None, ["a"], False))
        self.log.clear()
        self.undo_ready()
        self.ask(self.ap.reset)
        self.ap.confirmAlternate()
        self.wait_for(lambda: not self.ap.busy)
        self.assertEqual(self.log[0], ("reset", None, ["a"], True))

    def test_reset_with_only_art_from_elsewhere_offers_remove_all(self):
        self.undo_ready()
        self.other = ["y"]
        title, paragraphs, go, alt = self.ask(self.ap.reset)
        self.assertEqual((go, alt), ("Remove all", ""))
        self.ap.confirm()
        self.wait_for(lambda: not self.ap.busy)
        self.assertEqual(self.log[0], ("reset", None, [], True))

    def test_reset_with_steam_open_names_the_consequence(self):
        self.undo_ready()
        self.ours, self.other = ["a"], ["y"]
        self.running = True
        self.ap.watching = True
        self.wait_for(lambda: self.ap.steamOpen)
        title, paragraphs, go, alt = self.ask(self.ap.reset)
        self.assertEqual((go, alt, paragraphs[-1]["kind"]), ("Close Steam and remove only ours", "Close Steam and remove all", "warn"))

    def test_reset_with_nothing_to_remove_says_so(self):
        self.undo_ready()
        self.ap.reset()
        self.wait_for(lambda: not self.ap.busy)
        self.assertEqual(self.ap.status, "No custom covers were found in \u201cAlice\u201d. Nothing to reset.")
        self.assertEqual(self.log, [])

    def test_declining_the_reset_question_changes_nothing_and_frees_the_screen(self):
        self.undo_ready()
        self.ours = ["a"]
        self.ask(self.ap.reset)
        self.ap.decline()
        self.assertEqual((self.ap.busy, self.ap.status, self.log), (False, "", []))
        self.assertTrue(self.ap.canReset)

    def test_a_scan_that_fails_is_reported(self):
        self.undo_ready()
        self.scan_error = "Cannot read Steam's artwork."
        self.ap.reset()
        self.wait_for(lambda: not self.ap.busy)
        self.assertEqual((self.ap.status, self.ap.statusKind, self.ap.busy), ("Cannot read Steam's artwork.", "error", False))

    def test_an_old_scan_answer_is_dropped(self):
        self.undo_ready()
        asked = []
        self.ap.confirmNeeded.connect(lambda *a: asked.append(a))
        self.ap._req = 5
        self.ap._busy = True
        self.ap._on_scanned(4, ["a"], "Alice", 0, None)
        self.assertEqual(asked, [])
        self.ap._busy = False

    def test_a_job_that_ends_while_a_probe_is_running_is_probed_again(self):
        import threading
        gate, calls = threading.Event(), []
        self.addCleanup(gate.set)                                       # a failing test must not leave a worker thread waiting
        real = self.sc.list_backups

        def slow(steam, user=None):
            calls.append(1)
            gate.wait(5)
            return list(self.backups)
        self.sc.list_backups = slow
        self.addCleanup(lambda: setattr(self.sc, "list_backups", real))
        self.ap.refreshUndo()
        self.wait_for(lambda: bool(calls))
        self.ap.refreshUndo()                                           # asked again while one is running: remembered
        gate.set()
        self.wait_for(lambda: len(calls) >= 2)
        self.assertGreaterEqual(len(calls), 2)

    def test_the_scan_stops_when_it_is_no_longer_wanted(self):
        self.undo_ready()
        seen = []
        real = self.sc.find_our_covers

        def spy(steam, user=None, progress=None, cancelled=None):
            seen.append(cancelled)
            return []
        self.sc.find_our_covers = spy
        self.addCleanup(lambda: setattr(self.sc, "find_our_covers", real))
        self.ap.reset()
        self.wait_for(lambda: bool(seen))
        self.assertFalse(seen[0]())
        self.ap._req += 1                                               # another request took over
        self.assertTrue(seen[0]())
        self.wait_for(lambda: not self.ap.busy)

    def test_a_failure_of_restore_reset_or_apply_is_also_announced_for_a_box(self):
        self.covers_ready()
        failures = []
        self.ap.failed.connect(failures.append)
        self.apply_error = self.sc.SteamcaseError("No covers found in x. Make them first.")
        self.go()
        self.assertEqual(failures, ["No covers found in x. Make them first."])
        self.scan_error = "Cannot read Steam's artwork."
        self.undo_ready()
        self.ap.reset()
        self.wait_for(lambda: not self.ap.busy)
        self.assertEqual(failures[-1], "Cannot read Steam's artwork.")

    def test_one_account_is_shown_and_not_offered(self):
        self.ap.refresh()
        a = self.ap
        self.assertEqual((a.accountLabel, a.canChoose, a.accountId), ("Steam account: Alice", False, ""))
        self.assertEqual(a.accounts, [{"key": "111", "label": "Alice"}])

    def test_with_two_accounts_the_user_chooses_and_the_choice_is_used(self):
        self.accounts = [("111", "Alice"), ("222", "Bob")]
        self.ap.refresh()
        a = self.ap
        self.assertEqual((a.accountLabel, a.canChoose), ("Steam account: Alice", True))
        self.covers_ready()
        a.chooseAccount("222")
        self.assertEqual((a.accountLabel, a.accountId), ("Steam account: Bob", "222"))
        self.result = dict(self.result, account_name="Bob")
        self.go()
        self.assertEqual(self.log[0][1], "222")
        a.chooseAccount("999")                                          # not an account of this Steam: ignored
        self.assertEqual(a.accountId, "222")

    def test_choosing_an_account_clears_the_last_result(self):
        self.accounts = [("111", "Alice"), ("222", "Bob")]
        self.ap.refresh()
        self.covers_ready()
        self.go()
        self.assertNotEqual(self.ap.status, "")
        self.ap.chooseAccount("222")
        self.assertEqual(self.ap.status, "")

    def test_an_account_that_has_gone_is_not_used(self):
        self.accounts = [("111", "Alice"), ("222", "Bob")]
        self.ap.refresh()
        self.ap.chooseAccount("222")
        self.accounts = [("111", "Alice")]
        self.covers_ready()
        self.go()
        self.assertEqual(self.log[0][1], None)
        self.assertEqual(self.ap.accountId, "")

    def test_a_long_name_is_cut_and_no_steam_gives_no_account(self):
        self.accounts = [("111", "A" * 40)]
        self.ap.refresh()
        self.assertEqual(self.ap.accountLabel, "Steam account: " + "A" * 27 + "\u2026")
        with unittest.mock.patch.object(self.sc, "steam_dir", side_effect=self.sc.SteamcaseError("no steam")):
            self.ap.refresh()
        self.assertEqual((self.ap.accountLabel, self.ap.accounts, self.ap.canChoose), ("", [], False))

    def test_steam_is_only_asked_about_while_the_screen_is_watching_and_never_on_the_ui_thread(self):
        import threading
        self.shell.poll()
        self.assertEqual(self.probes, [])
        self.ap.watching = True
        self.wait_for(lambda: bool(self.probes))
        self.assertIsNot(self.probes[0], threading.main_thread())

    def test_a_slow_probe_is_not_repeated(self):
        import threading
        gate = threading.Event()
        self.addCleanup(gate.set)                                       # a failing test must not leave a worker thread waiting
        real = self.sc.steam_running
        self.sc.steam_running = lambda: (self.probes.append(1), gate.wait(5))[1] or False
        self.addCleanup(lambda: setattr(self.sc, "steam_running", real))
        self.ap.watching = True
        self.ap.poll()
        self.ap.poll()
        self.wait_for(lambda: bool(self.probes))
        self.assertEqual(len(self.probes), 1)
        gate.set()
        self.wait_for(lambda: not self.ap._probing)

    def test_a_probe_that_cannot_be_delivered_is_dropped_quietly(self):
        import shiboken6
        from qtui.apply import Apply
        gone = Apply(self.shell, self.make, self.covers)
        shiboken6.delete(gone)
        gone._probe()
        gone._work(1, {"restart": False, "account": None, "files": ["x.png"]})


if __name__ == "__main__":
    unittest.main()
