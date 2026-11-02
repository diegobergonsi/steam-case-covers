# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""safefile.read_small_file: the one way the app reads a small file the user (or anything else) controls."""
import os, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import safefile


def run_python(code, limit_mb=800, timeout=15):
    """The code in a separate process with a memory limit and a time limit, so a reader that never ends cannot hurt the test run.
    Returns (finished, output): finished is False when the time ran out."""
    script = ("try:\n    import resource; resource.setrlimit(resource.RLIMIT_AS, (%d << 20, %d << 20))\n"
              "except (ImportError, ValueError, OSError):\n    pass\n"
              "import sys; sys.path.insert(0, %r)\nimport safefile\n%s\n") % (limit_mb, limit_mb, HERE, code)
    try:
        r = subprocess.run([sys.executable, "-I", "-c", script], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, ""
    return r.returncode == 0, (r.stdout.strip() or r.stderr.strip()[-200:])


class Reading(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.path = os.path.join(self.tmp, "f.json")

    def write(self, data, path=None):
        with open(path or self.path, "wb") as f:
            f.write(data)

    def test_a_normal_file_is_read_whole(self):
        self.write(b'{"a": 1}')
        self.assertEqual(safefile.read_small_file(self.path, 100), b'{"a": 1}')

    def test_the_limit_is_inclusive(self):
        self.write(b"x" * 100)
        self.assertEqual(len(safefile.read_small_file(self.path, 100)), 100)
        self.write(b"x" * 101)
        with self.assertRaises(safefile.FileTooBig):
            safefile.read_small_file(self.path, 100)

    def test_a_missing_file_is_an_ordinary_os_error(self):
        with self.assertRaises(FileNotFoundError):
            safefile.read_small_file(self.path, 100)

    def test_all_refusals_are_os_errors_so_old_handlers_still_catch_them(self):
        self.assertTrue(issubclass(safefile.NotRegularFile, OSError) and issubclass(safefile.FileTooBig, OSError))

    def test_a_folder_is_not_a_file(self):
        os.mkdir(self.path)
        with self.assertRaises(safefile.NotRegularFile):
            safefile.read_small_file(self.path, 100)

    def test_a_link_is_refused_unless_links_are_followed(self):
        real = os.path.join(self.tmp, "real.json")
        self.write(b"[1]", real)
        try:
            os.symlink(real, self.path)
        except (OSError, NotImplementedError):
            self.skipTest("no symbolic links here")
        with self.assertRaises(safefile.NotRegularFile):
            safefile.read_small_file(self.path, 100)
        self.assertEqual(safefile.read_small_file(self.path, 100, follow_links=True), b"[1]")

    @unittest.skipUnless(hasattr(os, "mkfifo"), "needs named pipes")
    def test_a_named_pipe_is_refused_without_waiting_for_it(self):
        os.mkfifo(self.path)
        for follow in (False, True):
            self.assertEqual(run_python("try:\n    safefile.read_small_file(%r, 100, follow_links=%r)\nexcept safefile.NotRegularFile:\n    print('refused')" % (self.path, follow)),
                             (True, "refused"), follow)

    @unittest.skipUnless(os.path.exists("/dev/zero"), "needs /dev/zero")
    def test_an_endless_device_is_refused_even_through_a_followed_link(self):
        os.symlink("/dev/zero", self.path)
        self.assertEqual(run_python("try:\n    safefile.read_small_file(%r, 100, follow_links=True)\nexcept safefile.NotRegularFile:\n    print('refused')" % self.path), (True, "refused"))
        self.assertEqual(run_python("try:\n    safefile.read_small_file('/dev/zero', 100, follow_links=True)\nexcept safefile.NotRegularFile:\n    print('refused')"), (True, "refused"))


class Callers(unittest.TestCase):
    """The places that read such files all go through it: none of them hangs or fills memory on a pipe or an endless device."""
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    @unittest.skipUnless(hasattr(os, "mkfifo") and os.path.exists("/dev/zero"), "needs named pipes and /dev/zero")
    def test_the_game_list_reader_refuses_a_pipe_and_an_endless_device(self):
        pipe = os.path.join(self.tmp, "p.json")
        os.mkfifo(pipe)
        zero = os.path.join(self.tmp, "z.json")
        os.symlink("/dev/zero", zero)
        for path in (pipe, zero, "/dev/zero"):
            finished, out = run_python("import steamcase as sc\ntry:\n    sc.owned_ids(%r)\nexcept sc.SteamcaseError as e:\n    print(e)" % path)
            self.assertTrue(finished, path)
            self.assertIn("not a regular file", out, path)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "needs named pipes")
    def test_the_games_page_reader_refuses_a_pipe(self):
        pipe = os.path.join(self.tmp, "games.html")
        os.mkfifo(pipe)
        finished, out = run_python("import completion\ntry:\n    completion.read_games_page(%r)\nexcept completion.PageError as e:\n    print(e)" % pipe)
        self.assertEqual((finished, out), (True, "That is not a plain file. Pick the .html file you saved."))


if __name__ == "__main__":
    unittest.main()
