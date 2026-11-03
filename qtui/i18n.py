# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""The words of the window in English and Brazilian Portuguese.

The English text in the code is the key: `tr("Cancel")` in Python and `qsTr("Cancel")` in QML both find "Cancel" in the table of the chosen language and fall back
to the same English text when there is no entry, so a new sentence works at once and is translated later. A plural is one key with both forms split by "|",
`trn("%n game|%n games", count)` or `qsTr("%n game|%n games", "", count)`, and each language picks the form its own rules ask for. Qt puts the number in at "%n".
The table of Portuguese is qtui/i18n_pt_br.py. The language starts from the system, a saved choice wins, and it can change while the window is open."""
import os

from PySide6.QtCore import QCoreApplication, QLocale, QTranslator

from qtui.i18n_pt_br import PT_BR

LANGUAGES = {"en": "English", "pt-BR": "Português (Brasil)"}
TABLES = {"en": {}, "pt-BR": PT_BR}
CONTEXT = "steamcase"


def detect(locale_name):
    """"pt-BR" for any Portuguese system (pt_BR, pt_PT, pt...), "en" for everything else."""
    name = (locale_name or "").replace("-", "_").lower()
    return "pt-BR" if name == "pt" or name.startswith("pt_") or name.startswith("pt.") else "en"


def system_language():
    """The language of this computer, or the one STEAMCASE_LANG asks for (a way to force it, and what the tests use)."""
    return detect(os.environ.get("STEAMCASE_LANG") or QLocale.system().name())


def choose(saved, system_name):
    """The language to start in: the saved choice when it is one we have, else the system's."""
    return saved if saved in LANGUAGES else detect(system_name)


def _form(language, n):
    """0 for the singular form, 1 for the plural one. English: only 1 is singular. Brazilian Portuguese: 0 and 1 are singular."""
    return 0 if (n == 1 if language == "en" else n in (0, 1)) else 1


def _pick(language, source, n=-1):
    """The text for `source` in `language` (the source itself when there is no entry); for a plural (n >= 0) the form that language asks for. "%n" is left in."""
    text = TABLES[language].get(source, source)
    if n >= 0 and "|" in text:
        forms = text.split("|")
        return forms[min(_form(language, n), len(forms) - 1)]
    return text


class Translator(QTranslator):
    """Answers every qsTr of the QML for one language (Qt puts the number in at %n itself)."""
    def __init__(self, language):
        super().__init__()
        self.language = language

    def translate(self, context, source, disambiguation=None, n=-1):
        return _pick(self.language, source, n)


_language = None
_translator = None


def language():
    """The language in use: the one set, else the system's."""
    return _language or system_language()


def set_language(code):
    """Use this language from now on: every tr, and every qsTr that is evaluated again. ValueError for one we do not have."""
    global _language, _translator
    if code not in LANGUAGES:
        raise ValueError("unknown language: %r" % (code,))
    _language = code
    if QCoreApplication.instance() is not None:
        if _translator is not None:
            QCoreApplication.removeTranslator(_translator)
        _translator = Translator(code)
        QCoreApplication.installTranslator(_translator)


def N_(text):
    """Marks a text that is defined where it cannot be translated yet (a constant): translate it with tr() where it is used."""
    return text


def tr(text):
    return _pick(language(), text)


def trn(text, n):
    """A plural: `text` has both forms, "%n game|%n games"; the number goes in at %n."""
    return _pick(language(), text, n).replace("%n", str(n))
