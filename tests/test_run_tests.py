# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""tools/run_tests.py: the parallel runner shares test classes out among processes."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
from run_tests import share_out


class ShareOut(unittest.TestCase):
    IDS = [f"m.Big.t{i}" for i in range(5)] + ["m.Small.a", "m.Small.b", "n.One.x"]

    def test_a_class_is_never_split_and_no_test_is_lost_or_doubled(self):
        buckets = share_out(self.IDS, 3)
        self.assertEqual(sorted(sum(buckets, [])), sorted(self.IDS))
        for cls in ("m.Big", "m.Small", "n.One"):
            self.assertEqual(sum(any(i.startswith(cls + ".") for i in b) for b in buckets), 1)

    def test_there_are_no_empty_processes_and_the_biggest_class_is_alone(self):
        buckets = share_out(self.IDS, 16)
        self.assertEqual(len(buckets), 3)
        self.assertEqual(sorted(len(b) for b in buckets), [1, 2, 5])


if __name__ == "__main__":
    unittest.main()
