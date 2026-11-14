# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""engine.shortcuts: the non-Steam shortcuts of an account, read from shortcuts.vdf."""
import os, shutil, struct, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine import shortcuts


def vdf(entries):
    """A shortcuts.vdf: entries is a list of (appid or None, name). appid is the signed number Steam stores."""
    out = b"\x00shortcuts\x00"
    for n, (appid, name) in enumerate(entries):
        out += b"\x00%d\x00" % n
        if appid is not None:
            out += b"\x02appid\x00" + struct.pack("<i", appid)
        out += b"\x01AppName\x00" + name.encode() + b"\x00\x01Exe\x00\"/x/game\"\x00\x08"
    return out + b"\x08\x08"


class Base(unittest.TestCase):
    def setUp(self):
        self.steam = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.steam, True)
        self.config = os.path.join(self.steam, "userdata", "111", "config")
        os.makedirs(self.config)

    def write(self, data):
        with open(os.path.join(self.config, "shortcuts.vdf"), "wb") as f:
            f.write(data)


class ReadShortcuts(Base):
    def test_reads_names_and_unsigned_ids(self):
        self.write(vdf([(-296592220, "A"), (1234567, "B")]))
        self.assertEqual(shortcuts.read_shortcuts(self.steam, "111"), {3998375076: "A", 1234567: "B"})

    def test_entry_without_an_appid_is_ignored(self):
        self.write(vdf([(None, "Old"), (1234567, "B")]))
        self.assertEqual(shortcuts.read_shortcuts(self.steam, "111"), {1234567: "B"})

    def test_a_missing_file_a_garbled_file_and_an_empty_file_give_nothing(self):
        self.assertEqual(shortcuts.read_shortcuts(self.steam, "111"), {})
        for blob in (b"not vdf", b"", b"\x00" * 50, b"\xff" * 50):
            with self.subTest(blob[:8]):
                self.write(blob)
                self.assertEqual(shortcuts.read_shortcuts(self.steam, "111"), {})

    def test_a_truncated_file_never_raises(self):
        data = vdf([(-296592220, "A"), (1234567, "Some longer name")])
        for cut in range(len(data) + 1):
            self.write(data[:cut])
            self.assertIsInstance(shortcuts.read_shortcuts(self.steam, "111"), dict)

    def test_a_file_over_the_cap_gives_nothing(self):
        self.write(b"\x00" * (shortcuts.MAX_SHORTCUTS + 1))
        self.assertEqual(shortcuts.read_shortcuts(self.steam, "111"), {})

    def test_no_account_folder_gives_nothing(self):
        self.assertEqual(shortcuts.read_shortcuts(tempfile.mkdtemp(), None), {})


class AddNonSteam(unittest.TestCase):
    def test_adds_only_shortcuts_with_art_and_returns_only_their_art(self):
        games = {1: "Real"}
        added = shortcuts.add_non_steam(games, {1: "/a1.png", 500: "/a500.png", 600: "/a600.png"}, {500: "Mine", 700: "No art"})
        self.assertEqual(games, {1: "Real", 500: "Mine"})
        self.assertEqual(added, {500: "/a500.png"})

    def test_never_renames_a_steam_game(self):
        games = {500: "Real game"}
        added = shortcuts.add_non_steam(games, {500: "/a.png"}, {500: "Shortcut with the same id"})
        self.assertEqual(games, {500: "Real game"})
        self.assertEqual(added, {500: "/a.png"})


if __name__ == "__main__":
    unittest.main()
