# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""engine/collections.py: the collections Steam keeps for an account, read from cloud-storage-namespace-1.json."""
import json
import os
import shutil
import tempfile
import unittest

from engine import collections


def entry(name, added=(), removed=(), **extra):
    value = {"id": "x", "name": name, "added": list(added), "removed": list(removed)}
    value.update(extra)
    return {"value": json.dumps(value), "timestamp": 1, "version": "1"}


class ReadCollections(unittest.TestCase):
    def setUp(self):
        self.steam = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.steam, True)
        self.folder = os.path.join(self.steam, "userdata", "1234", "config", "cloudstorage")
        os.makedirs(self.folder)
        self.path = os.path.join(self.folder, "cloud-storage-namespace-1.json")

    def write(self, data, raw=False):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(data if raw else json.dumps(data))

    def read(self):
        return collections.read_collections(self.steam, "1234")

    def test_plain_collections_are_read(self):
        self.write([["user-collections.favorite", entry("Favorites", [1, 2])],
                    ["user-collections.uc-abc", entry("100% Games", [3, 4], [3])]])
        got = self.read()
        self.assertEqual([c.id for c in got], ["user-collections.favorite", "user-collections.uc-abc"])
        self.assertEqual([c.name for c in got], ["Favorites", "100% Games"])
        self.assertEqual([c.appids for c in got], [frozenset({1, 2}), frozenset({4})])      # what was removed is not a member

    def test_dynamic_deleted_and_nameless_are_skipped(self):
        deleted = entry("Gone", [1])
        deleted["is_deleted"] = True
        self.write([["user-collections.a", entry("Dynamic", [], filterSpec={"nFormatVersion": 2})],
                    ["user-collections.b", deleted],
                    ["user-collections.c", entry("", [1])],
                    ["user-collections.d", {"value": json.dumps({"added": [1]})}]])
        self.assertEqual(self.read(), [])

    def test_ids_that_are_not_numbers_are_skipped(self):
        self.write([["user-collections.a", entry("Odd", [1, "2", "x", None, 3.5, True])]])
        self.assertEqual(self.read()[0].appids, frozenset({1, 2}))

    def test_odd_files_give_nothing_and_do_not_raise(self):
        for text in ("not json", "{}", '["a", 1]', '[["user-collections.x", "text"]]',
                     '[["user-collections.x", {"value": "not json"}]]', '[["user-collections.x", {"value": "[1]"}]]',
                     '[["user-collections.x", {"value": "{\\"name\\": \\"N\\", \\"added\\": 5}"}]]', '[[1, {}]]'):
            with self.subTest(text=text):
                self.write(text, raw=True)
                self.assertEqual(self.read(), [])

    def test_hostile_numbers_and_nesting_do_not_raise(self):
        self.write(json.dumps([["user-collections.a", {"value": json.dumps({"name": "N", "added": ["9" * 5000, 1]})}]]), raw=True)
        self.assertEqual(self.read()[0].appids, frozenset({1}))                              # the id with 5000 digits is skipped, the rest stays
        self.write("[" * 200000, raw=True)                                                  # fits under the size limit, nests far too deep
        self.assertEqual(self.read(), [])
        value = "[" * 200000
        self.write(json.dumps([["user-collections.a", {"value": value}]]), raw=True)
        self.assertEqual(self.read(), [])

    def test_a_missing_file_and_an_account_without_a_folder_give_nothing(self):
        self.assertEqual(self.read(), [])
        self.assertEqual(collections.read_collections(self.steam, "9999"), [])

    def test_a_link_and_a_huge_file_are_refused(self):
        self.write([["user-collections.a", entry("Fine", [1])]])
        self.assertEqual(len(self.read()), 1)
        real = os.path.join(self.steam, "real.json")
        os.replace(self.path, real)
        try:
            os.symlink(real, self.path)
        except (OSError, NotImplementedError, AttributeError):
            self.skipTest("no symbolic links here")
        self.assertEqual(self.read(), [])
        os.remove(self.path)
        with open(self.path, "wb") as f:
            f.write(b" " * (collections.MAX_FILE + 1))
        self.assertEqual(self.read(), [])

    def test_other_keys_are_ignored(self):
        self.write([["something-else.a", entry("Not ours", [1])]])
        self.assertEqual(self.read(), [])


if __name__ == "__main__":
    unittest.main()
