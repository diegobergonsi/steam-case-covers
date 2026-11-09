# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""The translation layer of the window (qtui/i18n.py): which language to start in, the words, the plurals, and changing language while it runs."""
import ast, os, re, sys, unittest

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

    def test_a_saved_choice_is_read_back_and_a_bad_or_missing_one_is_ignored(self):
        """The shell starts in the saved language when there is one (see Shell.__init__) and in the system's otherwise."""
        import tempfile
        from qtui import settings
        path = os.path.join(tempfile.mkdtemp(), "settings.json")
        self.addCleanup(__import__("shutil").rmtree, os.path.dirname(path), True)
        self.assertIsNone(settings.load_language(path))
        for code in ("en", "pt-BR"):
            settings.save_language(code, path)
            self.assertEqual(settings.load_language(path), code)
        with open(settings.language_path(path), "w") as f:
            f.write("klingon")
        self.assertIsNone(settings.load_language(path))
        self.assertEqual(settings.LANGUAGE_CODES, tuple(i18n.LANGUAGES))


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

    def test_the_english_help_is_the_template_with_the_key_of_this_computer(self):
        from qtui import system
        i18n.set_language("en")
        self.assertEqual(system.page_help(), system.PAGE_HELP_TEMPLATE % system.SAVE_KEY)


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
                self.assertTrue(Blanks.same_blanks(a, b), key[:70])
                self.assertEqual(sorted(set(re.findall(r"%n", a))), sorted(set(re.findall(r"%n", b))) if "%n" in a else [], key[:70])

    def test_a_translation_keeps_the_spaces_around_it(self):
        for key, text in self.table.items():
            self.assertEqual((key[:1] == " ", key[-1:] == " "), (text[:1] == " ", text[-1:] == " "), repr(key[:50]))

    def test_the_words_that_must_stay_the_same_did_not_change(self):
        for word in ("Steam Case Covers",):
            self.assertIn(self.table.get(word, word), (word,))

    def test_the_christmas_theme_is_natal_in_portuguese(self):
        self.assertEqual(self.table["Christmas"], "Natal")


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
    between pieces. The QML scanner lives in tools/i18n_keys.py, next to the one that finds the keys."""
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
        import i18n_keys
        cls.keys = i18n_keys

    def test_no_qml_text_is_glued_to_a_translated_piece(self):
        qml = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "qtui", "qml")
        for name in sorted(os.listdir(qml)):
            if name.endswith(".qml"):
                with open(os.path.join(qml, name), encoding="utf-8") as f:
                    self.assertEqual(self.keys.glued(f.read()), [], name)

    def test_the_glue_guard_sees_the_shapes_it_is_meant_to_catch(self):
        for glued in ('qsTr("(optional)") + hint', 'qsTr("%n game", "", f(x)) + y', 'qsTr("Hi %1").arg(a) + b', 'label + ", " + qsTr("Done")', 'a + qsTr("x")',
                      'qsTr("a\\\\") + b'):
            self.assertTrue(self.keys.glued(glued), glued)
        for fine in ('qsTr("Hi %1").arg(a)', 'x + " \\u00b7 " + qsTr("%n step|%n steps", "", n)', 'x + " \u00b7 " + qsTr("%n step|%n steps", "", n)'):
            self.assertEqual(self.keys.glued(fine), [], fine)

    def test_an_unclosed_call_is_an_error_that_says_so(self):
        with self.assertRaisesRegex(ValueError, "unclosed"):
            self.keys.glued('qsTr("a"')

    def test_no_portuguese_message_is_a_fragment(self):
        """A piece starts with punctuation, or with a space and a small letter, or ends with punctuation that opens something, or with a word and a space."""
        from qtui.i18n_pt_br import PT_BR
        piece = re.compile(r"^\s*[,.:;)]|^ [a-z]|[,:(]\s*$|\w $")
        self.assertEqual([k[:60] for k in PT_BR if piece.search(k)], [])


class Blanks(unittest.TestCase):
    """The blanks of a message and of its translation: a numbered blank (%1, %2) may move, the others (%s, %d, %%) are filled in order."""
    @staticmethod
    def same_blanks(english, translation):
        numbered = lambda t: sorted(re.findall(r"%\d", t))
        ordered = lambda t: re.findall(r"%%|%[sd]", t)
        return numbered(english) == numbered(translation) and ordered(english) == ordered(translation)

    def test_numbered_blanks_may_be_reordered_and_the_others_may_not(self):
        self.assertTrue(self.same_blanks("%1, %2", "%2, %1"))
        self.assertTrue(self.same_blanks("%1 (%2 to %3)", "%3 a %2 (%1)"))
        self.assertTrue(self.same_blanks("%s and %s", "%s e %s"))
        self.assertFalse(self.same_blanks("%1", "%1 %2"))
        self.assertFalse(self.same_blanks("%1, %2", "%1"))
        self.assertFalse(self.same_blanks("%s and %d", "%d e %s"))


@need_qt
class ThemeLabels(unittest.TestCase):
    def test_every_theme_has_a_label_to_translate(self):
        from engine import steamcase as sc
        from qtui import reasons
        self.assertEqual(set(reasons.THEME_LABELS), {"classic", *sc.THEMES})


@need_qt
class CaseNames(unittest.TestCase):
    """How a group's case is named: one message with a blank for the colour, so each language puts the colour where it wants it."""
    def test_the_steam_case_in_a_colour_is_named_in_both_languages(self):
        from qtui import cases, tones
        self.addCleanup(i18n.set_language, i18n.language())
        red = next(x for x in tones.swatches() if x["name"] == "Red")
        for language, red_name, custom in (("en", "Steam case, red", "Steam case, custom colour"), ("pt-BR", "Case da Steam, vermelho", "Case da Steam, cor personalizada")):
            i18n.set_language(language)
            self.assertEqual(cases.case_label({"tone": (red["hue"], red["sat"], red["val"])}), red_name, language)
            self.assertEqual(cases.case_label({"tone": (1, 2, 3)}), custom, language)


if __name__ == "__main__":
    unittest.main()


class PortugueseFile(unittest.TestCase):
    def test_no_english_text_is_translated_twice(self):
        """A dict literal keeps only the last of two equal keys, without a word: the first translation would be dead text."""
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "qtui", "i18n_pt_br.py")
        seen, twice = set(), []
        for node in ast.walk(ast.parse(open(path, encoding="utf-8").read())):
            if isinstance(node, ast.Dict):
                for key in node.keys:
                    if isinstance(key, ast.Constant) and isinstance(key.value, str):
                        if key.value in seen:
                            twice.append(key.value)
                        seen.add(key.value)
        self.assertEqual(twice, [])

    def test_the_gender_of_the_words_of_the_reset_message_agrees(self):
        from qtui.i18n_pt_br import PT_BR
        self.assertIn("os grupos não foram alterados", PT_BR["Everything was reset to the starting point. Your saved cases, covers and groups were not changed."])
        self.assertEqual(PT_BR["Skipped"], "Ignorados")
