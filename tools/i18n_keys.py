#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Every English text of the window that is meant to be translated, as the keys of qtui/i18n_pt_br.py: what tr(), trn(), N_() and _t() get in the Python code, what
qsTr() gets in the QML, and the long help texts the window passes to QML. Used by the tests (every key has a translation, no translation is left over) and by
whoever adds a language."""
import ast, glob, json, os, re

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
MARKERS = {"tr", "trn", "N_", "_t"}


def python_keys():
    keys = {}
    for path in sorted(glob.glob(os.path.join(ROOT, "qtui", "*.py")) + [os.path.join(ROOT, "steamcase.py"), os.path.join(ROOT, "completion.py")]):
        tree = ast.parse(open(path, encoding="utf-8").read())
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in MARKERS and n.args:
                arg = n.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    keys.setdefault(arg.value, os.path.basename(path))
    return keys


_QSTR = re.compile(r'qsTr\(\s*("(?:[^"\\]|\\.)*")')


def qml_keys():
    keys = {}
    for path in sorted(glob.glob(os.path.join(ROOT, "qtui", "qml", "*.qml"))):
        for m in _QSTR.finditer(open(path, encoding="utf-8").read()):
            keys.setdefault(json.loads(m.group(1)), os.path.basename(path))       # a QML string literal is a JSON string: → and \" are decoded the same way
    return keys


def help_keys():
    import steamcase as sc
    from qtui import system
    return {t: "help" for t in (sc.FAMILY_HELP, sc.AUTO_ART_HELP, system.CUSTOM_ART_HELP, system.PAGE_HELP_TEMPLATE)}


def all_keys():
    keys = {}
    for part in (python_keys(), qml_keys(), help_keys()):
        for k, v in part.items():
            keys.setdefault(k, v)
    return keys


if __name__ == "__main__":
    ks = all_keys()
    print(len(ks), "keys,", sum(len(k) for k in ks), "characters")
