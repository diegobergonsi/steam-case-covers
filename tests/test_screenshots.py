# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""tools/take_screenshots.py still runs: it drives the window through the four screens in both languages, so a renamed property or screen would break it silently.
It runs here on the offscreen platform (the pages are not drawn there, so only the files and their sizes are checked; a person looks at the pictures)."""
import os
import subprocess
import sys
import tempfile
import unittest

try:
    from PySide6.QtGui import QGuiApplication
except ImportError:
    QGuiApplication = None
need_qt = unittest.skipIf(QGuiApplication is None, "PySide6 missing")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@need_qt
class ScreenshotScript(unittest.TestCase):
    def test_it_writes_the_eight_pictures_of_the_readme_and_leaves_the_real_home_alone(self):
        from PIL import Image
        out = tempfile.mkdtemp()
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        run = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "take_screenshots.py"), out, "--scale", "1"], env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(run.returncode, 0, run.stderr[-600:])
        sizes = {"home": (900, 900), "look": (900, 900), "100": (900, 1000), "cases": (900, 1000)}
        for screen, size in sizes.items():
            for suffix in ("", "-pt"):
                path = os.path.join(out, "screenshot-%s%s.png" % (screen, suffix))
                self.assertTrue(os.path.exists(path), path)
                with Image.open(path) as picture:
                    self.assertEqual(picture.size, size, path)
        self.assertEqual(sorted(os.listdir(out)), sorted("screenshot-%s%s.png" % (s, x) for s in sizes for x in ("", "-pt")))


if __name__ == "__main__":
    unittest.main()
