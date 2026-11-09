#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Run the whole test suite on every core: the test classes are shared out among one `python -m unittest` process per core (about 5 minutes become under one).
`python tools/run_tests.py` runs everything; `-j N` sets the number of processes. CI keeps `python -m unittest discover`."""
import argparse, os, subprocess, sys, unittest
from collections import defaultdict

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
TESTS = os.path.join(ROOT, "tests")


def test_ids(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from test_ids(test)
        else:
            yield test.id()


def share_out(ids, workers):
    """Buckets of test ids, a class never split (its tests may share set-up), the biggest classes first into the lightest bucket."""
    classes = defaultdict(list)
    for one in ids:
        classes[one.rsplit(".", 1)[0]].append(one)
    buckets = [[] for _ in range(max(1, min(workers, len(classes))))]
    for group in sorted(classes.values(), key=len, reverse=True):
        min(buckets, key=len).extend(group)
    return buckets


def main(argv=None):
    ask = argparse.ArgumentParser(description=__doc__)
    ask.add_argument("-j", type=int, default=os.cpu_count() or 1, help="number of processes (default: one per core)")
    args = ask.parse_args(argv)
    os.chdir(ROOT)
    sys.path[:0] = [ROOT, TESTS]
    ids = list(test_ids(unittest.defaultTestLoader.discover(TESTS)))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(filter(None, [ROOT, TESTS, os.environ.get("PYTHONPATH")])), QT_QPA_PLATFORM=os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    jobs = [subprocess.Popen([sys.executable, "-m", "unittest", *bucket], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
            for bucket in share_out(ids, args.j)]
    failed = 0
    for job in jobs:
        out = job.communicate()[0]
        if job.returncode:
            failed += 1
            print(out)
    print(f"{len(ids)} tests in {len(jobs)} processes: {'FAILED, ' + str(failed) + ' process(es) above' if failed else 'OK'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
