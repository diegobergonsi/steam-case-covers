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
    for path in sorted(glob.glob(os.path.join(ROOT, "qtui", "*.py")) + glob.glob(os.path.join(ROOT, "engine", "*.py"))):
        tree = ast.parse(open(path, encoding="utf-8").read())
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in MARKERS and n.args:
                arg = n.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    keys.setdefault(arg.value, os.path.basename(path))
    return keys


_QSTR = re.compile(r'qsTr\(\s*("(?:[^"\\]|\\.)*")')
_SEPARATOR = re.compile(r'"\s*(?:\\u00b7|\u00b7)\s*"\s*$')            # the " \u00b7 " between a way's name and its step count is not a word


def qsTr_calls(text):
    """(start, end) of every `qsTr(...)` call in QML text, with the `.arg(...)` calls that follow it. Parentheses inside a quoted string do not count."""
    def close(i, start):                                 # `i` is just after an opening parenthesis; the index just after its closing one
        depth, quote, escaped = 1, None, False
        while depth:
            if i >= len(text):
                raise ValueError("unclosed parenthesis in: " + text[start:start + 40])
            c = text[i]
            if quote:
                if escaped:
                    escaped = False
                elif c == "\\":
                    escaped = True
                elif c == quote:
                    quote = None
            elif c in "\"'":
                quote = c
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            i += 1
        return i
    for m in re.finditer(r"qsTr\(", text):
        end = close(m.end(), m.start())
        while text.startswith(".arg(", end):
            end = close(end + 5, m.start())
        yield m.start(), end


def glued(text):
    """The places in QML text where a translated message is glued to something with `+`: a translator cannot move a word between pieces. Only the separator
    between a way's name and its step count may sit next to one."""
    found = []
    for start, end in qsTr_calls(text):
        if re.match(r"\s*\+", text[end:]):
            found.append(text[start:end + 12])
        before = text[:start].rstrip()
        if before.endswith("+") and not _SEPARATOR.search(before[:-1].rstrip()):
            found.append(text[max(0, start - 30):end])
    return found


def qml_keys():
    keys = {}
    for path in sorted(glob.glob(os.path.join(ROOT, "qtui", "qml", "*.qml"))):
        text = open(path, encoding="utf-8").read()
        for start, _ in qsTr_calls(text):
            m = _QSTR.match(text, start)
            if m:
                keys.setdefault(json.loads(m.group(1)), os.path.basename(path))       # a QML string literal is a JSON string: → and \" are decoded the same way
    return keys


def help_keys():
    from engine import steamcase as sc
    from qtui import system
    return {t: "help" for t in (sc.FAMILY_HELP, sc.AUTO_ART_HELP, sc.SOFTWARE_HELP, sc.NON_STEAM_HELP, system.CUSTOM_ART_HELP, system.PAGE_HELP_TEMPLATE)}


def all_keys():
    keys = {}
    for part in (python_keys(), qml_keys(), help_keys()):
        for k, v in part.items():
            keys.setdefault(k, v)
    return keys


if __name__ == "__main__":
    ks = all_keys()
    print(len(ks), "keys,", sum(len(k) for k in ks), "characters")
