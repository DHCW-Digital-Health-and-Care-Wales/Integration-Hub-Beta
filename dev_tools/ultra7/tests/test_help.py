import gc
import tkinter as tk
import unittest

from ultra7.help_content import build_help_topics, get_shortcuts, search_help_topics
from ultra7.ui.help_dialog import AboutDialog, HelpDialog
from ultra7.ui.themes import get_theme


def _tk_available() -> bool:
    try:
        root = tk.Tk()
    except tk.TclError:
        return False
    root.destroy()
    return True


class TestHelpContent(unittest.TestCase):
    def test_topics_are_well_formed_and_unique(self) -> None:
        topics = build_help_topics()
        self.assertGreaterEqual(len(topics), 10)
        ids = [t.id for t in topics]
        self.assertEqual(len(ids), len(set(ids)))
        for topic in topics:
            self.assertTrue(topic.title)
            self.assertTrue(topic.category)
            self.assertTrue(topic.summary)
            self.assertTrue(topic.body)

    def test_search_filters_by_keyword(self) -> None:
        all_topics = build_help_topics()
        self.assertEqual(len(search_help_topics("", all_topics)), len(all_topics))

        nhs_hits = search_help_topics("Modulus 11", all_topics)
        self.assertTrue(any(t.id == "iteration-fields" for t in nhs_hits))

        mllp_hits = search_help_topics("2575", all_topics)
        self.assertTrue(any(t.id == "endpoints" for t in mllp_hits))

        stream_hits = search_help_topics("Pipelined burst", all_topics)
        self.assertTrue(any(t.id == "endpoints" for t in stream_hits))

        self.assertEqual(search_help_topics("xyznonexistentterm123", all_topics), [])

    def test_shortcuts_reflect_accelerator(self) -> None:
        mac = get_shortcuts("Cmd")
        win = get_shortcuts("Ctrl")
        self.assertTrue(any(k == "Cmd+S" for k, _ in mac))
        self.assertTrue(any(k == "Ctrl+S" for k, _ in win))


@unittest.skipUnless(_tk_available(), "requires a Tk display")
class TestHelpDialog(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self) -> None:
        self.root.destroy()
        gc.collect()

    def test_help_dialog_opens_searches_and_switches_topics(self) -> None:
        dlg = HelpDialog(self.root, initial_topic_id="shortcuts", theme=get_theme("Dark"))
        content = dlg.reader.get("1.0", "end-1c")
        self.assertIn("Keyboard Shortcuts", content)

        dlg.select_topic("hl7-reference")
        self.assertIn("HL7 v2.x Quick Reference", dlg.reader.get("1.0", "end-1c"))

        dlg._search_var.set("Scrub PII")
        dlg._apply_search()
        self.assertGreaterEqual(dlg.topic_listbox.size(), 1)
        self.assertIn("PII", dlg.reader.get("1.0", "end-1c"))

        dlg._search_var.set("no_match_anywhere_999")
        dlg._apply_search()
        self.assertEqual(dlg.topic_listbox.size(), 0)
        self.assertIn("No matching help topics", dlg.reader.get("1.0", "end-1c"))
        dlg.destroy()

    def test_about_dialog_opens_cleanly(self) -> None:
        dlg = AboutDialog(self.root, theme=get_theme("Dracula"))
        dlg.destroy()


if __name__ == "__main__":
    unittest.main()
