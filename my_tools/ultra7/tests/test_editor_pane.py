import gc
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import filedialog, messagebox
from unittest.mock import patch

from ultra7.models import Message
from ultra7.ui.editor_pane import EditorPane


def _tk_available() -> bool:
    try:
        root = tk.Tk()
    except tk.TclError:
        return False
    root.destroy()
    return True


@unittest.skipUnless(_tk_available(), "requires a Tk display")
class TestEditorPaneDisabledMessages(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()
        self.pane = EditorPane(self.root, on_change=lambda: None)

    def tearDown(self) -> None:
        self.root.destroy()
        # Finalize any leftover Tk Variable objects on this (main) thread now,
        # instead of leaving them for the GC to collect on some other thread later.
        gc.collect()

    def test_disabled_message_shows_off_prefix_and_muted_colour(self) -> None:
        self.pane.set_messages([
            Message(name="A01", format="hl7", content="MSH|...", enabled=True),
            Message(name="A02", format="hl7", content="MSH|...", enabled=False),
        ])
        self.pane._refresh_listbox()

        self.assertEqual(self.pane.listbox.get(0), "A01")
        self.assertEqual(self.pane.listbox.get(1), "[off] A02")
        self.assertEqual(self.pane.listbox.itemcget(0, "foreground"), "")
        self.assertEqual(self.pane.listbox.itemcget(1, "foreground"), "#6B7280")

    def test_toggling_updates_listbox_colour(self) -> None:
        self.pane.set_messages([Message(name="A01", format="hl7", content="MSH|...")])
        self.pane._refresh_listbox(select=0)
        self.assertEqual(self.pane.listbox.itemcget(0, "foreground"), "")

        self.pane._toggle_message_enabled()
        self.assertEqual(self.pane.listbox.get(0), "[off] A01")
        self.assertEqual(self.pane.listbox.itemcget(0, "foreground"), "#6B7280")

        self.pane._toggle_message_enabled()
        self.assertEqual(self.pane.listbox.get(0), "A01")
        self.assertEqual(self.pane.listbox.itemcget(0, "foreground"), "")


@unittest.skipUnless(_tk_available(), "requires a Tk display")
class TestEditorPaneMultiSelect(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()
        self.pane = EditorPane(self.root, on_change=lambda: None)
        self.pane.set_messages([
            Message(name="A01", format="hl7", content="MSH|...A01"),
            Message(name="A02", format="hl7", content="MSH|...A02"),
            Message(name="A03", format="hl7", content="MSH|...A03"),
        ])
        self.pane._refresh_listbox()

    def tearDown(self) -> None:
        self.root.destroy()
        gc.collect()

    def test_listbox_allows_multiple_selection(self) -> None:
        self.pane.listbox.selection_set(0, 2)  # select all three
        self.assertEqual(self.pane.listbox.curselection(), (0, 1, 2))

    def test_get_selected_messages_returns_all_highlighted(self) -> None:
        self.pane.listbox.selection_set(0)
        self.pane.listbox.selection_set(2)
        messages = self.pane.get_selected_messages()
        self.assertEqual([m.name for m in messages], ["A01", "A03"])

    def test_get_selected_messages_empty_when_nothing_selected(self) -> None:
        self.assertEqual(self.pane.get_selected_messages(), [])

    def test_bulk_toggle_disables_all_when_any_enabled(self) -> None:
        self.pane._messages[1].enabled = False  # mixed state: A01/A03 enabled, A02 disabled
        self.pane.listbox.selection_set(0, 2)

        self.pane._toggle_message_enabled()

        self.assertFalse(self.pane._messages[0].enabled)
        self.assertFalse(self.pane._messages[1].enabled)
        self.assertFalse(self.pane._messages[2].enabled)
        # Selection is preserved after the bulk toggle.
        self.assertEqual(self.pane.listbox.curselection(), (0, 1, 2))

    def test_bulk_toggle_enables_all_when_all_disabled(self) -> None:
        for message in self.pane._messages:
            message.enabled = False
        self.pane._refresh_listbox()
        self.pane.listbox.selection_set(0, 2)

        self.pane._toggle_message_enabled()

        self.assertTrue(all(m.enabled for m in self.pane._messages))

    def test_toggle_button_reflects_mixed_selection(self) -> None:
        self.pane._messages[1].enabled = False
        self.pane.listbox.selection_set(0, 2)
        self.pane._update_toggle_enabled_button_for_selection()
        self.assertEqual(self.pane._toggle_enabled_btn.cget("text"), "Disable")

        for message in self.pane._messages:
            message.enabled = False
        self.pane._update_toggle_enabled_button_for_selection()
        self.assertEqual(self.pane._toggle_enabled_btn.cget("text"), "Enable")


@unittest.skipUnless(_tk_available(), "requires a Tk display")
class TestEditorPaneLoadFromDisk(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()
        self.pane = EditorPane(self.root, on_change=lambda: None)

    def tearDown(self) -> None:
        self.root.destroy()
        gc.collect()

    def test_loads_multiple_files_at_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path_a = Path(tmp) / "a.hl7"
            path_b = Path(tmp) / "b.json"
            path_a.write_text("MSH|^~\\&|A|B|C|D|20250101||ADT^A01|1|P|2.5", encoding="utf-8")
            path_b.write_text('{"a": 1}', encoding="utf-8")

            with patch.object(filedialog, "askopenfilenames", return_value=(str(path_a), str(path_b))):
                self.pane._load_from_disk()

        names = [m.name for m in self.pane.get_messages()]
        formats = [m.format for m in self.pane.get_messages()]
        self.assertEqual(names, ["a.hl7", "b.json"])
        self.assertEqual(formats, ["hl7", "json"])
        # The last loaded file is selected in the editor.
        self.assertEqual(self.pane.listbox.curselection(), (1,))

    def test_cancelled_dialog_is_noop(self) -> None:
        with patch.object(filedialog, "askopenfilenames", return_value=()):
            self.pane._load_from_disk()
        self.assertEqual(self.pane.get_messages(), [])

    def test_unreadable_file_reports_error_but_loads_the_rest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            good_path = Path(tmp) / "good.json"
            good_path.write_text("{}", encoding="utf-8")
            missing_path = Path(tmp) / "missing.json"

            with patch.object(
                filedialog, "askopenfilenames", return_value=(str(missing_path), str(good_path))
            ), patch.object(messagebox, "showerror") as mock_error:
                self.pane._load_from_disk()

            self.assertTrue(mock_error.called)
            self.assertEqual([m.name for m in self.pane.get_messages()], ["good.json"])


if __name__ == "__main__":
    unittest.main()
