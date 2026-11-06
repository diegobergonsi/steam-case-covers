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

    def test_a_games_line_and_a_group_caption_are_translated(self):
        from qtui import i18n
        from qtui.cases import games_line, group_caption
        self.addCleanup(i18n.set_language, "en")
        i18n.set_language("en")
        self.assertEqual((games_line("PlayStation 5", 3), group_caption("Dad's games", "Xbox One", 1)), ("PlayStation 5 \u00b7 3 games", "Dad's games \u00b7 Xbox One \u00b7 1 game"))
        i18n.set_language("pt-BR")
        self.assertEqual((games_line("PlayStation 5", 3), group_caption("Dad's games", "Xbox One", 3)), ("PlayStation 5 \u00b7 3 jogos", "Dad's games \u00b7 Xbox One \u00b7 3 jogos"))

    def test_the_games_in_a_group_in_both_languages(self):
        from qtui import i18n
        self.addCleanup(i18n.set_language, "en")
        i18n.set_language("en")
        self.assertEqual([i18n.trn("%n game|%n games", n) for n in (1, 3)], ["1 game", "3 games"])
        i18n.set_language("pt-BR")
        self.assertEqual([i18n.trn("%n game|%n games", n) for n in (1, 3)], ["1 jogo", "3 jogos"])

    def test_the_step_counts_of_the_two_ways_in_both_languages(self):
        from qtui import i18n
        self.addCleanup(i18n.set_language, "en")
        i18n.set_language("en")
        self.assertEqual([i18n.trn("%n step|%n steps", n) for n in (1, 5, 6)], ["1 step", "5 steps", "6 steps"])
        i18n.set_language("pt-BR")
        self.assertEqual([i18n.trn("%n step|%n steps", n) for n in (1, 5, 6)], ["1 passo", "5 passos", "6 passos"])

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
class PageHelp(unittest.TestCase):
    """The help of the games page names the key that saves a page: Ctrl+S, or Cmd+S on a Mac. Its Portuguese must follow."""
    def tearDown(self):
        i18n.set_language("en")

    def test_the_portuguese_help_names_the_key_of_this_computer(self):
        from unittest import mock
        from qtui import system
        i18n.set_language("pt-BR")
        for key in ("Ctrl+S", "Cmd+S"):
            with mock.patch.object(system, "SAVE_KEY", key):
                text = system.page_help()
            self.assertIn("Como salvar a página", text)
            self.assertIn("aperte %s e salve" % key, text)
            self.assertIn("100%:", text)

    def test_the_english_help_is_the_text_of_page_help_constant(self):
        from qtui import system
        i18n.set_language("en")
        self.assertEqual(system.page_help(), system.PAGE_HELP)


@need_qt
class Table(unittest.TestCase):
    """qtui/i18n_pt_br.py against what the code asks for (tools/i18n_keys.py)."""
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
        import i18n_keys
        cls.keys = i18n_keys.all_keys()
        from qtui.i18n_pt_br import PT_BR
        cls.table = PT_BR

    def test_every_text_of_the_window_has_a_portuguese_translation(self):
        self.assertEqual(sorted(k[:70] for k in self.keys if k not in self.table), [])

    def test_the_table_has_nothing_left_over_from_texts_that_are_gone(self):
        self.assertEqual(sorted(k[:70] for k in self.table if k not in self.keys), [])

    def test_the_portuguese_says_case_not_caixa(self):
        self.assertEqual(sorted(k[:50] for k, v in self.table.items() if "caixa" in v.lower()), [])      # the project calls a case a "case" in Portuguese

    def test_placeholders_and_plural_forms_match_the_english(self):
        import re
        for key, text in self.table.items():
            plural = "%n" in key and "|" in key
            english, portuguese = (key.split("|"), text.split("|")) if plural else ([key], [text])
            self.assertEqual(len(english), len(portuguese), key[:70])
            for a, b in zip(english, portuguese):
                self.assertEqual(re.findall(r"%%|%1|%[sd]", a), re.findall(r"%%|%1|%[sd]", b), key[:70])
                self.assertEqual(sorted(set(re.findall(r"%n", a))), sorted(set(re.findall(r"%n", b))) if "%n" in a else [], key[:70])

    def test_a_translation_keeps_the_spaces_around_it(self):
        for key, text in self.table.items():
            self.assertEqual((key[:1] == " ", key[-1:] == " "), (text[:1] == " ", text[-1:] == " "), repr(key[:50]))

    def test_the_words_that_must_stay_the_same_did_not_change(self):
        for word in ("Steam Case Covers", "Halloween"):
            self.assertIn(self.table.get(word, word), (word,))


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


class WholeSentences(unittest.TestCase):
    """A message is one sentence with a blank where the changing part goes (`%1` in QML, `%s` in Python), never pieces glued together: a translator cannot move a word
    between pieces."""
    def test_no_qml_text_is_glued_to_a_translated_piece(self):
        import re
        qml = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "qtui", "qml")
        for name in sorted(os.listdir(qml)):
            if name.endswith(".qml"):
                with open(os.path.join(qml, name), encoding="utf-8") as f:
                    self.assertEqual(re.findall(r"qsTr\([^)]*\)\s*\+|\+\s*qsTr\(", f.read()), [], name)

    @need_qt
    def test_no_portuguese_message_is_a_fragment(self):
        from qtui.i18n_pt_br import PT_BR
        fragments = [k[:60] for k in PT_BR if k.lstrip(" ")[:1] in ",.:;)" or k.rstrip(" ")[-1:] in ",:("]
        self.assertEqual(fragments, [])


if __name__ == "__main__":
    unittest.main()
