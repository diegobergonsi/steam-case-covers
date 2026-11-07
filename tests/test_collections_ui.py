# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""The Steam collections on the Games step: the Picker's side (what is shown, ticking by adding or replacing) and the window's side (the buttons, the question).
(The reader of Steam's file is tested in test_collections.py.)"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_qtui import PickerBase, WindowClicks, need_qt


class CollectionFiles:
    """Puts a Steam collections file in the fake Steam folder of a PickerBase test."""

    def write_collections(self, collections, account="1234"):
        """`collections` is [(key suffix, name, [app ids])]; a name with extra keys is a dict {"name", "added", "filterSpec"...}."""
        folder = os.path.join(self.tmp, "userdata", account, "config", "cloudstorage")
        os.makedirs(folder, exist_ok=True)
        pairs = []
        for key, name, added in collections:
            pairs.append(["user-collections." + key, {"value": json.dumps({"id": key, "name": name, "added": added, "removed": []}), "version": "1"}])
        with open(os.path.join(folder, "cloud-storage-namespace-1.json"), "w", encoding="utf-8") as f:
            json.dump(pairs, f)

    def labels(self):
        return [c["label"] for c in self.picker.collections]


@need_qt
class CollectionTests(CollectionFiles, PickerBase):
    """The Games step knows the player's Steam collections: buttons that tick a whole collection, adding or replacing."""

    def many(self):
        self.write_collections([("few", "Few", [1]), ("many", "Many", [1, 2, 99]), ("elsewhere", "Elsewhere", [98, 99]), ("apple", "Apple", [3])])
        self.load()
        return "user-collections.many"

    def test_buttons_count_only_games_on_screen_sorted_and_labelled(self):
        self.many()
        self.assertEqual(self.labels(), ["Many (2)", "Apple (1)", "Few (1)"])          # most games first, then by name; "Elsewhere" has none on screen
        self.assertEqual([c["count"] for c in self.picker.collections], [2, 1, 1])

    def test_no_file_means_no_collections(self):
        self.load()
        self.assertEqual(self.picker.collections, [])

    def test_installed_only_counts_installed_games(self):
        self.library = {1: None}
        self.many()
        self.assertEqual(self.labels(), ["Few (1)", "Many (1)"])                           # equal counts: by name

    def test_the_plan_asks_only_when_something_is_ticked_and_it_would_change(self):
        many = self.many()
        plan = self.picker.collectionPlan(many)
        self.assertEqual((plan["name"], plan["games"], plan["ticked"], plan["afterAdd"], plan["ask"]), ("Many", 2, 0, 2, False))
        self.picker.toggle(3)
        plan = self.picker.collectionPlan(many)
        self.assertEqual((plan["ticked"], plan["afterAdd"], plan["ask"]), (1, 3, True))
        self.picker.applyCollection(many, "replace")
        self.assertFalse(self.picker.collectionPlan(many)["ask"])                        # the click would change nothing

    def test_an_unknown_collection_has_no_games_and_no_question(self):
        self.many()
        plan = self.picker.collectionPlan("user-collections.nope")
        self.assertEqual((plan["games"], plan["ask"]), (0, False))

    def test_add_and_replace(self):
        many = self.many()
        self.picker.toggle(3)
        self.picker.applyCollection(many, "add")
        self.assertEqual(self.picker.selection(), [1, 2, 3])
        self.picker.applyCollection(many, "replace")
        self.assertEqual(self.picker.selection(), [1, 2])
        self.picker.applyCollection(many, "nonsense")
        self.picker.applyCollection("user-collections.nope", "replace")
        self.assertEqual(self.picker.selection(), [1, 2])

    def test_the_search_does_not_matter(self):
        many = self.many()
        self.picker.toggle(3)
        self.picker.query = "forza"                                                       # game 3 is ticked but hidden
        plan = self.picker.collectionPlan(many)
        self.assertEqual((plan["ticked"], plan["ask"]), (1, True))
        self.picker.applyCollection(many, "add")
        self.assertEqual((self.picker.selection(), self.picker.selectedCount), ([1, 2, 3], 3))
        self.picker.applyCollection(many, "replace")
        self.assertEqual(self.picker.selection(), [1, 2])

    def test_a_hostile_collections_file_does_not_stop_the_games_from_loading(self):
        folder = os.path.join(self.tmp, "userdata", "1234", "config", "cloudstorage")
        os.makedirs(folder)
        with open(os.path.join(folder, "cloud-storage-namespace-1.json"), "w") as f:
            f.write("[" * 200000)
        self.load()
        self.assertEqual((len(self.picker.rows), self.picker.collections), (3, []))

    def test_a_new_game_list_drops_the_buttons_and_an_old_id_does_nothing(self):
        many = self.many()
        self.shell.library.installedOnly = not self.shell.library.installedOnly         # another game list: the picker starts again
        self.assertEqual(self.picker.collections, [])
        self.picker.applyCollection(many, "add")
        self.assertEqual(self.picker.selection(), [])

    def test_the_account_chosen_in_apply_is_used(self):
        from unittest import mock
        self.write_collections([("a", "First account", [1])], account="1111")
        self.write_collections([("b", "Second account", [2])], account="2222")
        self.load()
        default = self.sc.pick_account(self.tmp)
        self.assertEqual(self.picker.collections[0]["name"], "First account" if default == "1111" else "Second account")
        other = "2222" if default == "1111" else "1111"
        with mock.patch.object(self.shell.apply, "accountChoice", lambda: other):
            self.picker.refreshCollections()
        self.assertEqual(self.picker.collections[0]["name"], "Second account" if other == "2222" else "First account")

    def test_a_collection_that_vanishes_from_the_file_is_gone_after_a_refresh(self):
        self.many()
        seen = []
        self.picker.collectionsChanged.connect(lambda: seen.append(1))
        self.picker.refreshCollections()
        self.assertEqual(seen, [])                                                        # nothing changed, nobody is told
        self.write_collections([("few", "Few", [1])])
        self.picker.refreshCollections()
        self.assertEqual((self.labels(), len(seen)), (["Few (1)"], 1))


@need_qt
class CollectionsWindow(CollectionFiles, WindowClicks, PickerBase):
    """The Games step in the real window, with Steam collections."""
    def setUp(self):
        super().setUp()
        self.start_window()

    # ----- Steam collections on the Games screen -----

    def open_games(self, collections):
        """Put these collections ([(key, name, [app ids])]) in the fake Steam and open the Games step; the buttons are there when it returns."""
        if collections:
            self.write_collections(collections)
        self.shell.startPath("manual")
        self.wait_for(lambda: self.picker.rows and (self.picker.collections or not collections))
        self.app.processEvents()

    def pill(self, key):
        return "games_collections_pill_user-collections." + key

    def test_no_collections_no_row(self):
        self.open_games([])
        self.assertFalse(self.item("games_collections").property("visible"))
        self.assertFalse(self.item("games_collections_label").property("visible"))

    def test_clicking_a_collection_ticks_its_games_without_a_question(self):
        self.open_games([("many", "Many", [1, 2])])
        self.assertEqual(self.item(self.pill("many")).property("text"), "Many (2)")
        self.click(self.pill("many"))
        self.assertEqual(self.picker.selection(), [1, 2])
        self.assertFalse(self.item("collections_dialog").property("visible"))

    def ask(self):
        """3 is ticked by hand, then the collection {1, 2} is clicked: the question is open."""
        self.open_games([("many", "Many", [1, 2])])
        self.click("games_row_3")
        self.click(self.pill("many"))
        self.assertTrue(self.item("collections_dialog").property("visible"))

    def test_with_ticks_the_dialog_asks_and_add_keeps_them(self):
        self.ask()
        self.assertEqual(self.text("collections_dlg_title"), "You already ticked 1 game")
        self.assertEqual(self.text("collections_dlg_p0"), "“Many” has 2 games on your list.")
        self.assertEqual(self.text("collections_dlg_p1"), "Add keeps your ticks and ticks the collection too: 3 games in total.")
        self.assertEqual(self.text("collections_dlg_p2"), "Replace unticks your games first: 2 games in total.")
        self.assertEqual([self.text("collections_dlg_confirm"), self.text("collections_dlg_alternate"), self.text("collections_dlg_cancel")],
                         ["Add them", "Replace them", "Cancel"])
        self.assertTrue(self.item("collections_dlg_cancel").property("activeFocus"))
        self.assertTrue(self.item("collections_dlg_confirm").property("filled"))
        self.click("collections_dlg_confirm")
        self.assertEqual(self.picker.selection(), [1, 2, 3])

    def test_replace_ticks_only_the_collection(self):
        self.ask()
        self.click("collections_dlg_alternate")
        self.assertEqual(self.picker.selection(), [1, 2])

    def test_cancel_and_escape_change_nothing(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        self.ask()
        self.click("collections_dlg_cancel")
        self.assertEqual((self.picker.selection(), self.item("collections_dialog").property("visible")), ([3], False))
        self.click(self.pill("many"))
        QTest.keyClick(self.root, Qt.Key_Escape)
        self.app.processEvents()
        self.assertEqual((self.picker.selection(), self.item("collections_dialog").property("visible")), ([3], False))

    def test_a_markup_name_is_plain_text_and_a_long_name_fits(self):
        self.open_games([("markup", "<b>Done</b>", [1]), ("long", "x" * 200, [1, 2])])
        pill = self.item(self.pill("markup"))
        self.assertEqual(pill.property("text"), "<b>Done</b> (1)")
        self.assertTrue(pill.property("plain"))                                              # drawn as text, not as markup
        self.assertLessEqual(self.item(self.pill("long")).width(), self.item("games_collections").width())

    def test_more_than_two_rows_show_the_link_and_hide_the_rest(self):
        self.open_games([("c%02d" % i, "Collection %02d" % i, [1]) for i in range(1, 26)])
        more = self.item("games_collections_more")
        self.assertTrue(more.property("visible"))
        self.assertEqual(more.property("text"), "Show all 25 collections")
        self.assertGreaterEqual(more.height(), 44)                                          # touch targets (docs/PRODUCT.md)
        self.assertGreaterEqual(self.item(self.pill("c01")).height(), 44)
        first, last = self.item(self.pill("c01")), self.item(self.pill("c25"))
        self.assertTrue(first.property("reachable"))
        self.assertEqual([last.property(p) for p in ("reachable", "enabled", "activeFocusOnTab")], [False, False, False])
        self.assertEqual(last.property("opacity"), 0)
        self.click("games_collections_more")
        self.assertTrue(last.property("reachable") and last.property("enabled") and last.property("activeFocusOnTab"))
        self.assertEqual(more.property("text"), "Show fewer")
        self.click("games_collections_more")
        self.assertEqual((last.property("reachable"), more.property("text")), (False, "Show all 25 collections"))

    def is_plain(self, name):
        """Whether the item draws its text as plain text (Python cannot read a Qt enum, so the question is asked inside QML)."""
        from PySide6.QtQml import QQmlEngine, QQmlExpression
        item = self.item(name)
        answer, error = QQmlExpression(QQmlEngine.contextForObject(item), item, "textFormat === Text.PlainText").evaluate()
        return answer is True

    def test_the_question_shows_a_name_as_typed_and_wraps_a_long_one(self):
        self.open_games([("markup", "<b>Done</b>", [1, 2]), ("long", "x" * 200, [1, 2])])
        self.click("games_row_3")
        self.click(self.pill("markup"))
        self.assertEqual(self.text("collections_dlg_p0"), "\u201c<b>Done</b>\u201d has 2 games on your list.")
        for name in ("collections_dlg_title", "collections_dlg_p0", "collections_dlg_p1"):
            self.assertTrue(self.is_plain(name), name)                                       # never read as markup
        self.click("collections_dlg_cancel")
        self.click(self.pill("long"))
        words = self.item("collections_dlg_p0")
        self.assertGreater(words.property("lineCount"), 1)                                   # a name with no spaces still wraps
        self.assertLessEqual(words.property("contentWidth"), words.width())

    def test_a_long_name_keeps_its_count_on_the_pill(self):
        self.open_games([("long", "x" * 200, [1, 2])])
        pill, count = self.item(self.pill("long")), self.item("games_collections_count_user-collections.long")
        self.assertEqual(count.property("text"), "(2)")
        self.assertLessEqual(count.x() + count.width(), pill.width())
        self.assertTrue(self.item("games_collections_text_user-collections.long").property("truncated"))   # only the name is cut

    def test_the_focus_ring_of_a_pill_is_not_cut_off(self):
        from PySide6.QtCore import QPointF
        self.open_games([("a", "A", [1]), ("b", "B", [2])])
        pill = self.item(self.pill("a"))
        pad = 5                                                                              # ringOffset + focusRing
        shown = self.item("games_collections_shown")
        at = pill.mapToItem(shown, QPointF(0, 0))
        self.assertGreaterEqual((at.x(), at.y()), (pad, pad))

    def test_a_few_collections_have_no_link(self):
        self.open_games([("a", "A", [1]), ("b", "B", [2]), ("c", "C", [3])])
        self.assertFalse(self.item("games_collections_more").property("visible"))

    def test_the_dialog_survives_a_collection_that_is_gone(self):
        self.ask()
        self.write_collections([("other", "Other", [1])])                                # Steam changed the file while the question was open
        self.picker.refreshCollections()
        self.click("collections_dlg_confirm")
        self.assertEqual(self.picker.selection(), [3])                                  # nothing was added, nothing broke
        self.assertFalse(self.item("collections_dialog").property("visible"))

    def test_the_new_texts_are_translated(self):
        self.open_games([("c%02d" % i, "Collection %02d" % i, [1]) for i in range(1, 26)])
        self.shell.setLanguage("pt-BR")                                                  # an open question keeps the words it was opened with
        self.app.processEvents()
        self.click("games_row_3")
        self.click(self.pill("c02"))
        for name in ("games_collections_label", "games_collections_more", "collections_dlg_title", "collections_dlg_p0", "collections_dlg_p1", "collections_dlg_p2",
                     "collections_dlg_confirm", "collections_dlg_alternate"):
            with self.subTest(name):
                self.assertNotRegex(self.text(name), r"^(Your collections|Show all|You already|“.*” has|Add keeps|Replace unticks|Add them|Replace them)")


if __name__ == "__main__":
    unittest.main()
