# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""The translation layer of the window (qtui/i18n.py): which language to start in, the words, the plurals, and changing language while it runs."""
import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtGui import QGuiApplication
except ImportError:
    QGuiApplication = None
need_qt = unittest.skipIf(QGuiApplication is None, "PySide6 missing")

if QGuiApplication is not None:
    from qtui import i18n


@need_qt
class Choosing(unittest.TestCase):
    def test_any_portuguese_system_starts_in_brazilian_portuguese_and_the_rest_in_english(self):
        for name in ("pt_BR", "pt-BR", "pt_PT", "pt", "PT_br.UTF-8"):
            self.assertEqual(i18n.detect(name), "pt-BR", name)
        for name in ("en_US", "en_GB", "es_ES", "de_DE", "", "C", "POSIX", None):
            self.assertEqual(i18n.detect(name), "en", name)

    def test_the_environment_can_force_the_language(self):
        old = os.environ.get("STEAMCASE_LANG")
        self.addCleanup(lambda: os.environ.pop("STEAMCASE_LANG", None) if old is None else os.environ.__setitem__("STEAMCASE_LANG", old))
        os.environ["STEAMCASE_LANG"] = "pt_BR"
        self.assertEqual(i18n.system_language(), "pt-BR")
        os.environ["STEAMCASE_LANG"] = "en"
        self.assertEqual(i18n.system_language(), "en")

    def test_a_saved_choice_wins_over_the_system_and_a_bad_one_is_ignored(self):
        self.assertEqual(i18n.choose("en", "pt_BR"), "en")
        self.assertEqual(i18n.choose("pt-BR", "en_US"), "pt-BR")
        self.assertEqual(i18n.choose("klingon", "pt_BR"), "pt-BR")
        self.assertEqual(i18n.choose(None, "en_US"), "en")
        self.assertEqual(i18n.choose("", "pt_BR"), "pt-BR")


@need_qt
class Words(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])

    def tearDown(self):
        i18n.set_language("en")

    def test_english_keeps_the_words_and_portuguese_replaces_the_known_ones(self):
        i18n.set_language("en")
        self.assertEqual(i18n.tr("Cancel"), "Cancel")
        i18n.set_language("pt-BR")
        self.assertEqual(i18n.tr("Cancel"), "Cancelar")
        self.assertEqual(i18n.tr("A sentence nobody translated"), "A sentence nobody translated")

    def test_plurals_follow_the_rules_of_each_language(self):
        i18n.set_language("en")
        self.assertEqual([i18n.trn("%n game|%n games", n) for n in (0, 1, 2)], ["0 games", "1 game", "2 games"])
        i18n.set_language("pt-BR")
        self.assertEqual([i18n.trn("%n game|%n games", n) for n in (0, 1, 2, 5)], ["0 jogo", "1 jogo", "2 jogos", "5 jogos"])   # Portuguese: 0 and 1 are singular

    def test_changing_the_language_changes_the_next_answer_and_back(self):
        i18n.set_language("pt-BR")
        self.assertEqual(i18n.language(), "pt-BR")
        i18n.set_language("en")
        self.assertEqual((i18n.language(), i18n.tr("Cancel")), ("en", "Cancel"))

    def test_an_unknown_language_is_refused_and_nothing_changes(self):
        i18n.set_language("pt-BR")
        with self.assertRaises(ValueError):
            i18n.set_language("fr")
        self.assertEqual(i18n.language(), "pt-BR")


@need_qt
class Saving(unittest.TestCase):
    def setUp(self):
        import shutil, tempfile
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.path = os.path.join(self.tmp, "settings.json")

    def test_the_choice_is_saved_next_to_the_settings_and_read_back(self):
        from qtui import settings
        self.assertIsNone(settings.load_language(self.path))
        self.assertTrue(settings.save_language("pt-BR", self.path))
        self.assertEqual(settings.load_language(self.path), "pt-BR")
        self.assertTrue(settings.save_language("en", self.path))
        self.assertEqual(settings.load_language(self.path), "en")

    def test_a_damaged_or_odd_file_is_no_choice(self):
        from qtui import settings
        target = settings.language_path(self.path)
        for content in ("", "klingon", "pt-BR\n\n", "x" * 5000, "\x00\x01"):
            with open(target, "w") as f:
                f.write(content)
            self.assertIn(settings.load_language(self.path), (None, "pt-BR"), repr(content[:10]))
        with open(target, "w") as f:
            f.write("klingon")
        self.assertIsNone(settings.load_language(self.path))
        self.assertFalse(settings.save_language("klingon", self.path))

    def test_the_settings_file_keeps_its_old_shape(self):
        from qtui import settings
        settings.save_language("pt-BR", self.path)
        settings.save_settings(dict(settings.DEFAULTS), self.path)
        import json
        with open(self.path) as f:
            self.assertEqual(list(json.load(f)), list(settings.SETTING_KEYS))


if __name__ == "__main__":
    unittest.main()
