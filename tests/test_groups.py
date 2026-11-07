# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""The store of groups of covers made by hand (engine/groups.py)."""
import json, os, shutil, sys, tempfile, unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine import groups as gr
from engine import steamcase as sc

RED = {"tone": [134, 100, 100]}
PS5 = {"platform": "ps5"}


def run_load(folder, limit_mb=800, timeout=15):
    """groups.load(folder) in a separate process with a memory limit and a time limit, so a loader that reads forever cannot hurt the test run.
    Returns (finished, printed): finished is False when the time ran out."""
    import subprocess
    code = ("import sys, json\n"
            "try:\n"
            "    import resource; resource.setrlimit(resource.RLIMIT_AS, (%d << 20, %d << 20))\n"
            "except (ImportError, ValueError, OSError):\n"
            "    pass                                    # no such limit here (macOS refuses it): the time limit still protects the run\n"
            "sys.path.insert(0, %r)\n"
            "from engine import groups\n"
            "print(json.dumps(groups.load(%r)))\n") % (limit_mb, limit_mb, os.path.dirname(os.path.dirname(os.path.abspath(__file__))), folder)
    try:
        r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, ""
    return r.returncode == 0, r.stdout.strip() or r.stderr.strip()[-300:]


class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.path = os.path.join(self.tmp, "groups.json")

    def read(self):
        with open(self.path, encoding="utf-8") as f:
            return f.read()

    def write(self, text):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(text)

    def test_no_file_is_no_groups(self):
        self.assertEqual(gr.load(self.tmp), [])
        self.assertEqual(gr.load(os.path.join(self.tmp, "nope")), [])

    def test_a_damaged_file_is_no_groups_and_is_left_where_it_is(self):
        for text in ("", "not json", "[]", "{}", '{"groups": 5}', '{"groups": {"a": 1}}', "null", '{"groups": [5, "x", null]}', "\x00\x01"):
            with self.subTest(text=text):
                self.write(text)
                self.assertEqual(gr.load(self.tmp), [])
                self.assertTrue(os.path.exists(self.path))

    def test_an_unreadable_file_is_no_groups(self):
        with open(self.path, "wb") as f:
            f.write(b"\xff\xfe\x00bad")
        self.assertEqual(gr.load(self.tmp), [])

    def test_a_round_trip_keeps_everything(self):
        groups, red = gr.assign([], "Red Steam Cases", RED, [3, 1, 2])
        groups, ps = gr.assign(groups, "PS5 games", PS5, [10])
        gr.save(self.tmp, groups)
        back = gr.load(self.tmp)
        self.assertEqual(back, groups)
        self.assertEqual([g["name"] for g in back], ["Red Steam Cases", "PS5 games"])
        self.assertEqual(sorted(back[0]["games"]), [1, 2, 3])

    def test_bad_entries_are_dropped_and_good_ones_kept(self):
        good = {"id": "g1", "name": "Good", "case": RED, "games": [1, 2]}
        bad = [
            {"id": "g2", "name": "", "case": RED, "games": [3]},                                  # no name
            {"id": "g3", "name": "x" * 41, "case": RED, "games": [3]},                            # name too long
            {"id": "g4", "name": "Case", "case": {"platform": "ps9"}, "games": [3]},              # unknown platform
            {"id": "g5", "name": "Tone", "case": {"tone": [400, 100, 100]}, "games": [3]},        # hue out of range
            {"id": "g6", "name": "Tone2", "case": {"tone": [1, 2]}, "games": [3]},                # not three numbers
            {"id": "g7", "name": "Both", "case": {"platform": "ps5", "tone": [1, 1, 1]}, "games": [3]},
            {"id": "g8", "name": "NoGames", "case": RED, "games": []},                           # empty group
            {"id": "g9", "name": "Text", "case": RED, "games": ["a", None]},                      # no usable games
            {"id": "bad id!", "name": "Id", "case": RED, "games": [3]},                           # the id goes in a PNG note: letters and digits only
            {"name": "NoId", "case": RED, "games": [3]},
            {"id": "ga", "name": "Control\x07", "case": RED, "games": [3]},
        ]
        self.write(json.dumps({"groups": [good] + bad}))
        self.assertEqual([g["name"] for g in gr.load(self.tmp)], ["Good"])

    def test_games_that_are_not_numbers_are_dropped_from_a_group(self):
        self.write(json.dumps({"groups": [{"id": "g1", "name": "A", "case": RED, "games": [1, "2", True, -4, 0, 1.5, 7, 7]}]}))
        self.assertEqual(gr.load(self.tmp)[0]["games"], [1, 7])

    def test_a_duplicate_name_or_id_or_game_keeps_the_first(self):
        self.write(json.dumps({"groups": [
            {"id": "g1", "name": "Same", "case": RED, "games": [1, 2]},
            {"id": "g2", "name": "same", "case": RED, "games": [3]},                               # the same name, whatever its case
            {"id": "g1", "name": "Other id", "case": RED, "games": [4]},                          # the same id
            {"id": "g3", "name": "Third", "case": PS5, "games": [2, 5]},                          # game 2 is already in the first group
        ]}))
        got = gr.load(self.tmp)
        self.assertEqual([(g["name"], g["games"]) for g in got], [("Same", [1, 2]), ("Third", [5])])

    def test_save_is_atomic(self):
        gr.save(self.tmp, gr.assign([], "A", RED, [1])[0])
        before = self.read()
        with mock.patch.object(os, "replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                gr.save(self.tmp, gr.assign([], "B", RED, [2])[0])
        self.assertEqual(self.read(), before)                      # the old file is intact
        self.assertEqual([n for n in os.listdir(self.tmp) if n != "groups.json"], [])           # and no temporary file is left

    def test_save_makes_the_folder(self):
        folder = os.path.join(self.tmp, "a", "b")
        gr.save(folder, gr.assign([], "A", RED, [1])[0])
        self.assertEqual(len(gr.load(folder)), 1)


class Edit(unittest.TestCase):
    def test_assign_makes_a_group_with_an_id_a_cover_note_can_hold(self):
        groups, gid = gr.assign([], "  Red Steam Cases  ", RED, [5, 5, 6])
        self.assertEqual(groups, [{"id": gid, "name": "Red Steam Cases", "case": RED, "games": [5, 6]}])
        self.assertRegex(gid, r"^[a-z0-9]{1,12}$")

    def test_the_same_name_and_case_adds_to_the_group(self):
        groups, gid = gr.assign([], "Red", RED, [1])
        groups, again = gr.assign(groups, "red", RED, [2, 3])
        self.assertEqual((again, len(groups), groups[0]["games"]), (gid, 1, [1, 2, 3]))

    def test_the_same_name_in_another_case_is_refused(self):
        groups, _ = gr.assign([], "Mine", RED, [1])
        with self.assertRaises(ValueError) as caught:
            gr.assign(groups, "Mine", PS5, [2])
        self.assertIn("Mine", str(caught.exception))

    def test_a_game_moves_to_its_new_group_and_an_empty_group_goes(self):
        groups, a = gr.assign([], "A", RED, [1, 2])
        groups, b = gr.assign(groups, "B", PS5, [1, 2])
        self.assertEqual([(g["name"], g["games"]) for g in groups], [("B", [1, 2])])           # A lost both games: it is gone
        groups, c = gr.assign(groups, "C", RED, [2])
        self.assertEqual([(g["name"], g["games"]) for g in groups], [("B", [1]), ("C", [2])])

    def test_invalid_input_is_refused_in_words(self):
        for name, case, games in (("", RED, [1]), ("   ", RED, [1]), ("x" * 41, RED, [1]), ("a\nb", RED, [1]), ("A", {"platform": "ps9"}, [1]),
                                   ("A", {"tone": [360, 0, 0]}, [1]), ("A", {"tone": [0, 101, 0]}, [1]), ("A", {}, [1]), ("A", RED, []), ("A", RED, ["x"]),
                                   ("A", RED, [0]), ("A", RED, [True]), ("A", "red", [1])):
            with self.subTest(name=name, case=case, games=games), self.assertRaises(ValueError):
                gr.assign([], name, case, games)

    def test_every_platform_and_a_tone_edge_are_valid(self):
        for p in sc.PLATFORMS:
            gr.assign([], p, {"platform": p}, [1])
        gr.assign([], "Edge", {"tone": [359, 0, 100]}, [1])
        gr.assign([], "Gold", {"tone": [sc.GOLD_HUE, 100, 100]}, [1])

    def test_the_custom_case_is_a_valid_group_case(self):
        groups, gid = gr.assign([], "Mine", {"platform": sc.CUSTOM}, [1, 2])
        self.assertEqual(groups[0]["case"], {"platform": "custom"})
        with tempfile.TemporaryDirectory() as d:
            gr.save(d, groups)
            self.assertEqual(gr.load(d), groups)

    def test_assign_does_not_change_the_list_it_was_given(self):
        groups, _ = gr.assign([], "A", RED, [1])
        before = json.dumps(groups)
        gr.assign(groups, "B", PS5, [1, 2])
        self.assertEqual(json.dumps(groups), before)

    def test_delete_members_and_drop_games(self):
        groups, a = gr.assign([], "A", RED, [1, 2])
        groups, b = gr.assign(groups, "B", PS5, [3])
        self.assertEqual(gr.members(groups, {a}), {1, 2})
        self.assertEqual(gr.members(groups, {a, b, "nope"}), {1, 2, 3})
        self.assertEqual(gr.members(groups, set()), set())
        self.assertEqual([g["name"] for g in gr.delete(groups, a)], ["B"])
        self.assertEqual(len(gr.delete(groups, "nope")), 2)
        dropped = gr.drop_games(groups, {2, 3, 99})
        self.assertEqual([(g["name"], g["games"]) for g in dropped], [("A", [1])])              # B lost its only game: gone



class Rename(unittest.TestCase):
    def two(self):
        groups, red = gr.assign([], "Red games", RED, [1, 2])
        groups, ps = gr.assign(groups, "Sony", PS5, [3])
        return groups, red, ps

    def test_rename_changes_only_the_name(self):
        groups, red, ps = self.two()
        out = gr.rename(groups, red, "  Crimson  ")
        self.assertEqual([(g["id"], g["name"], g["case"], g["games"]) for g in out],
                         [(red, "Crimson", RED, [1, 2]), (ps, "Sony", PS5, [3])])

    def test_rename_to_the_same_name_in_other_capitals_is_allowed(self):
        groups, red, _ = self.two()
        self.assertEqual(gr.rename(groups, red, "RED GAMES")[0]["name"], "RED GAMES")

    def test_rename_to_another_groups_name_is_refused(self):
        groups, red, _ = self.two()
        for taken in ("Sony", "sony", "  SONY "):
            with self.assertRaises(ValueError) as caught:
                gr.rename(groups, red, taken)
            self.assertIn("Sony", str(caught.exception))

    def test_rename_refuses_empty_41_letters_and_line_breaks(self):
        groups, red, _ = self.two()
        for bad in ("", "   ", "x" * 41, "two\nlines"):
            with self.assertRaises(ValueError):
                gr.rename(groups, red, bad)
        self.assertEqual(gr.rename(groups, red, "x" * 40)[0]["name"], "x" * 40)

    def test_rename_of_an_unknown_id_is_refused(self):
        groups, _, _ = self.two()
        with self.assertRaises(ValueError):
            gr.rename(groups, "nope", "Fine")

    def test_rename_does_not_change_the_list_it_was_given(self):
        groups, red, _ = self.two()
        before = json.dumps(groups)
        gr.rename(groups, red, "Other")
        self.assertEqual(json.dumps(groups), before)


class AddGames(unittest.TestCase):
    def three(self):
        groups, red = gr.assign([], "Red games", RED, [1, 2])
        groups, ps = gr.assign(groups, "Sony", PS5, [3])
        return groups, red, ps

    def test_the_games_move_into_the_group_with_this_id(self):
        groups, red, ps = self.three()
        out = gr.add_games(groups, ps, [1])
        self.assertEqual([(g["id"], g["games"]) for g in out], [(red, [2]), (ps, [3, 1])])

    def test_a_group_left_without_games_goes(self):
        groups, red, ps = self.three()
        self.assertEqual([g["id"] for g in gr.add_games(groups, red, [3])], [red])

    def test_each_game_once_and_in_order(self):
        groups, red, ps = self.three()
        self.assertEqual(gr.add_games(groups, red, [2, 5, 5])[0]["games"], [1, 2, 5])

    def test_an_unknown_group_or_no_games_is_refused(self):
        groups, red, ps = self.three()
        for bad in (("nope", [1]), (red, []), (red, [0]), (red, ["x"])):
            with self.assertRaises(ValueError):
                gr.add_games(groups, *bad)

    def test_it_does_not_change_the_list_it_was_given(self):
        groups, red, ps = self.three()
        before = json.dumps(groups)
        gr.add_games(groups, red, [3])
        self.assertEqual(json.dumps(groups), before)


class DamagedFile(unittest.TestCase):
    """groups.json is read when the window opens, so a damaged, huge or odd file must give no groups, quickly, and never take the app down."""
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.path = os.path.join(self.tmp, "groups.json")

    def good(self, games):
        return json.dumps({"groups": [{"id": "gabc12345", "name": "A", "case": {"platform": "ps5"}, "games": games}]})

    @unittest.skipUnless(hasattr(os, "mkfifo"), "needs named pipes")
    def test_a_named_pipe_is_not_waited_for(self):
        os.mkfifo(self.path)
        self.assertEqual(run_load(self.tmp), (True, "[]"))

    @unittest.skipUnless(os.path.exists("/dev/zero"), "needs /dev/zero")
    def test_a_link_to_an_endless_file_is_not_read(self):
        os.symlink("/dev/zero", self.path)
        self.assertEqual(run_load(self.tmp), (True, "[]"))

    def test_a_link_to_a_good_file_is_not_followed(self):
        real = os.path.join(self.tmp, "elsewhere.json")
        with open(real, "w") as f:
            f.write(self.good([1]))
        try:
            os.symlink(real, self.path)
        except (OSError, NotImplementedError):
            self.skipTest("no symbolic links here")
        self.assertEqual(gr.load(self.tmp), [])

    def test_a_file_over_the_size_limit_is_ignored(self):
        with open(self.path, "w") as f:
            f.write(" " * (gr.MAX_BYTES + 10) + self.good([1]))
        self.assertEqual(gr.load(self.tmp), [])
        with open(self.path, "w") as f:
            f.write(self.good([1]))
        self.assertEqual([g["games"] for g in gr.load(self.tmp)], [[1]])             # the control: a normal file still loads

    def test_deeply_nested_json_gives_no_groups(self):
        with open(self.path, "w") as f:
            f.write("[" * 100000)
        self.assertEqual(run_load(self.tmp), (True, "[]"))

    def test_a_group_with_very_many_games_loads_quickly_and_is_capped(self):
        import time
        with open(self.path, "w") as f:
            f.write(self.good(list(range(1, 150001))))
        t = time.time()
        got = gr.load(self.tmp)
        self.assertLess(time.time() - t, 5)
        self.assertLessEqual(len(got[0]["games"]), sc.MAX_APPS)

    def test_a_directory_in_the_place_of_the_file_gives_no_groups(self):
        os.mkdir(self.path)
        self.assertEqual(gr.load(self.tmp), [])

if __name__ == "__main__":
    unittest.main()
