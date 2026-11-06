# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""The design tokens: the colours and numbers in qtui/qml/Theme.qml against docs/ui-guide.md, docs/DESIGN.md and .impeccable/design.json, the contrast the guide
promises (WCAG 2.2 AA, on every fill a colour is drawn on), and the rules that keep every colour, size and time in Theme.qml. No window is needed.
Other tests import `THEME` to compare what the window draws with the theme."""
import colorsys
import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QML_DIR = os.path.join(ROOT, "qtui", "qml")

try:
    from PySide6.QtGui import QColor
except ImportError:
    QColor = None
need_qt = unittest.skipIf(QColor is None, "PySide6 missing")


def read(*parts):
    """A text file of the repository, as UTF-8 on every system."""
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


_THEME_TEXT = read("qtui", "qml", "Theme.qml")
THEME = dict(re.findall(r'readonly property color (\w+): "(#[0-9a-fA-F]{6})"', _THEME_TEXT))
HOVER_LIFT = float(re.search(r"readonly property real hoverLift: ([\d.]+)", _THEME_TEXT).group(1))          # the choice button under the mouse is raised, lighter by this
MENU_DARKER = float(re.search(r"navBg: Qt\.darker\(bg, ([\d.]+)\)", _THEME_TEXT).group(1))                  # the menu panel is the window colour, darker by this


def _rgb(colour):
    """0 to 1 red, green, blue of a #rrggbb string or of a 0 to 255 tuple."""
    if isinstance(colour, str):
        return [int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return [x / 255 for x in colour]


def contrast(a, b):
    """WCAG contrast ratio of two colours (#rrggbb or 0 to 255 tuples)."""
    def luminance(colour):
        r, g, b = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in _rgb(colour)]
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


# Qt's `lighter` and `darker`, kept in Python because the test job without Qt runs these tests too; `test_the_hover_and_menu_colours_match_qt` keeps the copy honest.
def _scale_brightness(colour, factor):
    h, s, v = colorsys.rgb_to_hsv(*_rgb(colour))
    v *= factor
    if v > 1:                                                     # past the top, Qt takes the excess off the saturation
        s, v = max(0.0, s - (v - 1)), 1.0
    return "#%02x%02x%02x" % tuple(round(x * 255) for x in colorsys.hsv_to_rgb(h, s, v))


def lighter(colour, factor):
    return _scale_brightness(colour, factor)


def darker(colour, factor):
    return _scale_brightness(colour, 1 / factor)


def fills():
    """The fills a colour is drawn on: the window, the menu panel, the card, the raised fill (the open step in the menu, the help bubble, the toast, a switched-off
    main button), that fill under the mouse, and the blue of the main button (also under the mouse)."""
    return {"bg": THEME["bg"], "navBg": darker(THEME["bg"], MENU_DARKER), "card": THEME["card"], "raised": THEME["raised"],
            "raisedHover": lighter(THEME["raised"], HOVER_LIFT), "accent": THEME["accent"], "accentHover": lighter(THEME["accent"], HOVER_LIFT)}


GUIDE_ROWS = {"Background": "bg", "Card": "card", "Raised": "raised", "Accent": "accent", "Text": "text", "Muted": "muted", "Faint": "faint", "Control edge": "edge",
              "Done": "done", "Warning": "warning", "Error": "error"}
DESIGN_NAMES = {"night-ground": "bg", "card-navy": "card", "card-raised": "raised", "control-edge": "edge", "text": "text", "text-muted": "muted", "text-faint": "faint",
                "sky-blue": "accent", "ink-on-blue": "accentInk", "done-green": "done", "caution-amber": "warning", "error-coral": "error", "shadow": "shadow"}


class Tokens(unittest.TestCase):
    """The colours in qtui/qml/Theme.qml are those of the docs, with the contrast the guide promises; nothing else holds a colour."""

    def test_the_guide_table_holds_the_themes_colours_row_by_row(self):
        guide = read("docs", "ui-guide.md")
        rows = {GUIDE_ROWS[label]: value for label, value in re.findall(r"^\| ([A-Za-z ]+) \| `(#[0-9a-f]{6})`", guide, re.M)}
        rows["accentInk"] = re.search(r"Text on the accent button is `(#[0-9a-f]{6})`", guide).group(1)
        self.assertEqual(rows, {k: THEME[k] for k in (*GUIDE_ROWS.values(), "accentInk")})

    def test_the_design_file_holds_the_themes_colours_by_name(self):
        front = read("docs", "DESIGN.md").split("---")[1]            # the block between the first two lines of dashes
        listed = dict(re.findall(r'^  ([\w-]+): "(#[0-9a-f]{6})"$', front.split("typography:")[0], re.M))
        self.assertEqual(listed, {name: THEME[key] for name, key in DESIGN_NAMES.items()})

    def test_the_design_sidecar_holds_the_themes_colours_by_name(self):
        meta = json.loads(read(".impeccable", "design.json"))["extensions"]["colorMeta"]
        self.assertEqual({name: meta[name]["canonical"] for name in DESIGN_NAMES}, {name: THEME[key] for name, key in DESIGN_NAMES.items()})

    def test_a_colour_written_in_the_prose_of_the_docs_is_one_of_the_themes(self):
        for name in ("DESIGN.md", "ui-guide.md"):
            self.assertLessEqual(set(re.findall(r"#[0-9a-f]{6}\b", read("docs", name))), set(THEME.values()), name)

    def test_the_main_text_colours_meet_the_rule_on_the_main_fills(self):
        """WCAG 2.2 AA: text 4.5 to 1, outlines 3 to 1. A switched-off control (60%) is left out, as the rule leaves it out. A few pairs here never occur in the window
        (green on the window colour, say): the grid is a little stricter than it needs to be."""
        f = fills()
        main = ("bg", "navBg", "card", "raised")
        pairs = [(c, fill, 4.5) for c in ("faint", "done", "error", "warning", "accent") for fill in main]
        pairs += [(c, fill, 4.5) for c in ("muted", "text") for fill in main + ("raisedHover",)]
        pairs += [("edge", fill, 3.0) for fill in main]
        pairs += [("accentInk", fill, 4.5) for fill in ("accent", "accentHover")]
        for fg, fill, need in pairs:
            with self.subTest("%s on %s" % (fg, fill)):
                self.assertGreaterEqual(contrast(THEME[fg], f[fill]), need)

    def test_the_ratios_in_the_guide_are_true(self):
        guide, f = read("docs", "ui-guide.md"), fills()
        rows = {"Accent": ("accent", "bg"), "Text": ("text", "card"), "Muted": ("muted", "card"), "Faint": ("faint", "card"), "Control edge": ("edge", "card"),
                "Done": ("done", "card"), "Warning": ("warning", "card"), "Error": ("error", "card")}
        for label, (fg, fill) in rows.items():
            row = re.search(r"^\| %s \|.*$" % label, guide, re.M)
            self.assertIsNotNone(row, "the colour table has no row for " + label)
            said = re.search(r"(\d+\.\d):1", row.group(0))
            self.assertIsNotNone(said, "the row of %s has no ratio" % label)
            self.assertEqual(said.group(1), "%.1f" % contrast(THEME[fg], f[fill]), label)
        said = re.search(r"Text on the accent button is `#[0-9a-f]{6}` \((\d+\.\d):1\)", guide)
        self.assertIsNotNone(said, "the guide says nothing about the text on the accent button")
        self.assertEqual(said.group(1), "%.1f" % contrast(THEME["accentInk"], THEME["accent"]))

    @need_qt
    def test_the_hover_and_menu_colours_match_qt(self):
        for colour, ours, qt in ((THEME["bg"], darker(THEME["bg"], MENU_DARKER), QColor(THEME["bg"]).darker(round(MENU_DARKER * 100))),
                                 (THEME["raised"], lighter(THEME["raised"], HOVER_LIFT), QColor(THEME["raised"]).lighter(round(HOVER_LIFT * 100))),
                                 (THEME["accent"], lighter(THEME["accent"], HOVER_LIFT), QColor(THEME["accent"]).lighter(round(HOVER_LIFT * 100)))):
            self.assertEqual(ours, qt.name(), colour)

    def test_the_guide_names_the_steps_like_the_window(self):
        text = read("docs", "ui-guide.md")
        self.assertIn("1. Game list, 2. Look, 3. 100% games (optional), 4. Make, 5. Add to Steam", text)
        self.assertNotIn("Extras", text.replace("Extras became", ""))

    def qml_files(self):
        for name in sorted(os.listdir(QML_DIR)):
            if name.endswith(".qml") and name != "Theme.qml":
                yield name, read("qtui", "qml", name)

    def test_only_the_guides_durations_are_used(self):
        for name, text in self.qml_files():
            self.assertEqual(re.findall(r"duration:\s*\d", text), [], name + ": a duration must go through Theme.dur")
            for n in re.findall(r"Theme\.dur\((\d+)\)", text):
                self.assertIn(int(n), (90, 120, 200, 260), "%s: %s ms is not in the guide" % (name, n))

    def test_no_loose_design_numbers(self):
        """Corner radius, text size, shadow and opacity values come from Theme (sizes of layout boxes may stay in the files)."""
        for name, text in self.qml_files():
            for pattern in (r"\bradius:\s*\d", r"pixelSize:\s*\d", r"shadow(?:Blur|Opacity|VerticalOffset):\s*-?\d", r"\bopacity:[^\n]*\d\.\d",
                            r"Qt\.lighter\([^)]*,\s*[\d.]+\)", r"(?:blur|brightness|saturation):\s*-?\d"):
                self.assertEqual(re.findall(pattern, text), [], "%s: %s" % (name, pattern))

    def test_no_loose_layout_numbers(self):
        """Sizes, spacing, margins, borders and positions come from Theme too (0 is allowed). Only Theme.qml may hold a number."""
        patterns = (r"\b(?:width|height|implicitWidth|implicitHeight|spacing)\s*:\s*(?:-(?!Theme)|[1-9])", r"\banchors\.\w*[mM]argins?\s*:\s*(?:-(?!Theme)|[1-9])",
                    r"\b[xy]\s*:\s*(?:-(?!Theme)|[1-9])", r"\bborder\.width\s*:[^\n]*[1-9]", r"\bsourceSize\.\w+\s*:\s*[1-9]", r"Theme\.\w+\s*[-+*/]\s*\d",
                    r"Math\.(?:min|max)\(\s*[1-9]", r"\bfont\.pixelSize\s*:\s*[1-9]")
        for name, text in self.qml_files():
            for pattern in patterns:
                self.assertEqual(re.findall(pattern, text), [], "%s: %s" % (name, pattern))

    def test_there_is_no_picture_behind_the_window(self):
        """The approved design has plain surfaces; a decorative backdrop was added once without asking and removed again."""
        self.assertEqual(re.findall(r"\bImage\s*\{", read("qtui", "qml", "Main.qml")), [], "the window itself has no picture")
        self.assertEqual(re.findall(r"\bImage\s*\{", read("qtui", "qml", "NavLink.qml")), ["Image {"], "the only picture in the window is the Discord icon of a navigation link")
        for name in os.listdir(QML_DIR):
            self.assertNotIn("backdrop", read("qtui", "qml", name).lower(), name)

    def test_every_component_is_in_the_guide(self):
        names = [m.group(1) for m in re.finditer(r"^(\w+) 1\.0 ", read("qtui", "qml", "qmldir"), re.M)]
        guide = read("docs", "ui-guide.md")
        for name in names:
            if name != "Theme" and not name.endswith("Screen"):
                self.assertIn("`%s`" % name, guide, "%s is not in the guide's component list" % name)

    def test_no_other_file_has_a_colour_of_its_own(self):
        for name, text in self.qml_files():
            self.assertEqual(re.findall(r"#[0-9a-fA-F]{3,8}\b", text), [], name)


if __name__ == "__main__":
    unittest.main()
