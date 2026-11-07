# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Touch targets (docs/PRODUCT.md): everything a finger taps has a tap area of at least 44 x 44 px, read from the built window.
Run:  QT_QPA_PLATFORM=offscreen python -m unittest tests.test_qtui_touch"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_qtui import QML_DIR, WindowCase, need_qt

TOUCH = 44                                                   # the size PRODUCT.md promises
REACH = 21                                                   # a tap this far from the middle of a small control must still reach it


def read(name):
    with open(os.path.join(QML_DIR, name), encoding="utf-8") as f:
        return f.read()


class TouchSize(unittest.TestCase):
    def test_the_one_touch_size_in_theme_is_44(self):
        self.assertIn("readonly property int touchMin: %d" % TOUCH, read("Theme.qml"))

    def test_the_design_file_says_44_and_not_36(self):
        with open(os.path.join(QML_DIR, "..", "..", "docs", "DESIGN.md"), encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn('height: "36px"', text)
        self.assertIn('height: "44px"', text)


@need_qt
class TouchTargetsInWindow(WindowCase):
    def assert_tappable(self, name):
        it = self.item(name)
        self.assertGreaterEqual(it.width(), TOUCH, name + " is too narrow for a finger")
        self.assertGreaterEqual(it.height(), TOUCH, name + " is too short for a finger")

    def tap(self, name, dx, dy):
        """A tap `dx`, `dy` px from the middle of the item."""
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtTest import QTest
        it = self.item(name)
        point = it.mapToScene(QPointF(it.width() / 2 + dx, it.height() / 2 + dy)).toPoint()
        QTest.mouseClick(self.root, Qt.LeftButton, Qt.NoModifier, point)
        self.app.processEvents()

    def edges(self, name):
        from PySide6.QtCore import QPointF
        it = self.item(name)
        top = it.mapToScene(QPointF(0, 0)).y()
        return top, top + it.height()

    def at_the_shortest_window(self):
        self.root.setProperty("width", self.root.property("minimumWidth"))
        self.root.setProperty("height", self.root.property("minimumHeight"))
        self.app.processEvents()

    def in_both_languages(self, check):
        for language in ("en", "pt-BR"):
            with self.subTest(language):
                self.shell.setLanguage(language)
                self.app.processEvents()
                check()

    # the window opens at a size it can be

    def test_the_window_opens_no_shorter_than_its_shortest_height(self):
        self.assertGreaterEqual(self.root.height(), self.root.property("minimumHeight"))

    # sizes of what is tapped

    def test_the_menu_the_links_and_the_buttons_are_tappable(self):
        def check(*names):
            for name in names + ("nav_home", "footer_discord", "footer_kofi", "footer_updates"):
                self.assert_tappable(name)
        self.in_both_languages(lambda: check("nav_link_start_over"))               # on Home the menu holds links to its sections
        self.shell.startPath("natural")                                                                # the steps show inside a way, and a hidden row has no size yet
        self.app.processEvents()
        self.in_both_languages(lambda: check("nav_game_list", "nav_look", "nav_hundred", "nav_make", "nav_add"))
        self.shell.go(1)
        self.assert_tappable("gamelist_next")
        self.assert_tappable("gamelist_installed")
        self.shell.go(2)
        self.assert_tappable("look_next")

    def test_the_look_step_controls_are_tappable(self):
        self.shell.go(2)
        self.app.processEvents()
        look = self.shell.look
        for name in (["look_swatch_%d" % i for i in range(len(look.swatchList))] + ["look_hue", "look_sat", "look_val"]
                     + ["look_theme_chip_" + t["key"] for t in look.themes]):
            with self.subTest(name):
                self.assert_tappable(name)

    # small controls: the drawn shape is small, a tap around it still counts

    def test_the_flags_are_drawn_small_and_a_tap_around_them_picks_the_language(self):
        self.shell.setLanguage("en")
        for dx, dy in ((-REACH, -REACH), (REACH, REACH), (-REACH, REACH), (REACH, -REACH)):
            with self.subTest((dx, dy)):
                self.shell.setLanguage("en")
                self.tap("language_pt", dx, dy)
                self.assertEqual(self.shell.language, "pt-BR")
        self.assertEqual((self.item("language_pt").width(), self.item("language_pt").height()), (32, 24))

    def test_a_tap_far_from_a_flag_does_not_pick_it(self):
        self.shell.setLanguage("en")
        self.tap("language_pt", 0, 30)
        self.assertEqual(self.shell.language, "en")

    def test_the_two_flags_do_not_share_a_tap(self):
        self.shell.setLanguage("pt-BR")
        self.tap("language_en", -REACH, 0)                       # the far side of the English flag is the title side, not the Portuguese flag
        self.assertEqual(self.shell.language, "en")
        self.shell.setLanguage("pt-BR")
        self.tap("language_en", REACH, 0)                        # its near side is still its own
        self.assertEqual(self.shell.language, "en")

    def test_the_i_circle_is_drawn_small_flush_with_its_row_and_a_tap_around_it_opens_it(self):
        from PySide6.QtCore import QPointF
        self.shell.go(1)
        self.app.processEvents()
        row, tip = self.item("gamelist_installed"), self.item("gamelist_installed_tip")
        self.assertEqual(tip.mapToScene(QPointF(tip.width(), 0)).x(), row.mapToScene(QPointF(row.width(), 0)).x())
        for dx, dy in ((-REACH, -REACH), (REACH, REACH)):
            with self.subTest((dx, dy)):
                tip.setProperty("pinned", False)
                self.tap("gamelist_installed_tip", dx, dy)
                self.assertTrue(tip.property("pinned"))
        tip.setProperty("pinned", False)
        self.tap("gamelist_installed_tip", 0, 30)
        self.assertFalse(tip.property("pinned"))

    # the shortest window still lays out

    def check_the_menu_fits(self):
        self.at_the_shortest_window()
        self.assertGreaterEqual(self.edges("nav_languages")[0] - 10, self.edges("nav_title")[1], "the flags' tap area starts under the title")
        self.assertLessEqual(self.edges("nav_languages")[1] + 10, self.edges("nav_home")[0], "the flags' tap area ends above the first menu row")
        self.assertLessEqual(self.edges("footer_updates")[1], self.root.property("height"), "the last link is inside the window")

    def test_at_the_shortest_window_the_menu_fits_in_both_languages(self):
        self.in_both_languages(self.check_the_menu_fits)

    def test_a_title_of_two_lines_still_leaves_the_flags_alone(self):
        self.item("nav_title").setProperty("text", "Steam Case Covers Steam Case Covers")      # on Windows the normal title is already two lines, so ask for two
        self.app.processEvents()
        self.assertEqual(self.item("nav_title").property("lineCount"), 2)
        self.check_the_menu_fits()

    def test_at_the_narrowest_window_the_look_step_stays_inside_its_cards(self):
        from PySide6.QtCore import QPointF

        def check():
            self.shell.go(2)
            self.at_the_shortest_window()
            look = self.shell.look
            for section, names in (("look_section_colour", ["look_swatch_%d" % i for i in range(len(look.swatchList))]),
                                   ("look_section_theme", ["look_theme_chip_" + t["key"] for t in look.themes])):
                card = self.item(section)
                right = card.mapToScene(QPointF(card.width(), 0)).x()
                for name in names:
                    it = self.item(name)
                    self.assertLessEqual(it.mapToScene(QPointF(it.width(), 0)).x(), right + 0.5, name)
        self.in_both_languages(check)


if __name__ == "__main__":
    unittest.main()
