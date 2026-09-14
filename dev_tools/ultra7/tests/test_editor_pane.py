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

    def test_move_single_message_up(self) -> None:
        self.pane.listbox.selection_set(1)
        self.pane._move(-1)
        self.assertEqual([m.name for m in self.pane.get_messages()], ["A02", "A01", "A03"])

    def test_move_single_message_down(self) -> None:
        self.pane.listbox.selection_set(1)
        self.pane._move(1)
        self.assertEqual([m.name for m in self.pane.get_messages()], ["A01", "A03", "A02"])

    def test_move_multiple_selected_messages_up(self) -> None:
        # A02 and A03 selected; moving up slides the block one position earlier.
        self.pane.listbox.selection_set(1)
        self.pane.listbox.selection_set(2)
        self.pane._move(-1)
        self.assertEqual([m.name for m in self.pane.get_messages()], ["A02", "A03", "A01"])

    def test_move_multiple_selected_messages_down(self) -> None:
        # A01 and A02 selected; moving down slides the block one position later.
        self.pane.listbox.selection_set(0)
        self.pane.listbox.selection_set(1)
        self.pane._move(1)
        self.assertEqual([m.name for m in self.pane.get_messages()], ["A03", "A01", "A02"])

    def test_move_preserves_relative_order_of_selected_messages(self) -> None:
        self.pane.listbox.selection_set(0)
        self.pane.listbox.selection_set(1)
        self.pane.listbox.selection_set(2)
        self.pane._move(1)
        self.assertEqual([m.name for m in self.pane.get_messages()], ["A01", "A02", "A03"])

    def test_move_ignores_when_nothing_selected(self) -> None:
        self.pane.listbox.selection_clear(0, tk.END)
        self.pane._move(-1)
        self.assertEqual([m.name for m in self.pane.get_messages()], ["A01", "A02", "A03"])

    def test_move_does_not_wrap_around(self) -> None:
        self.pane.listbox.selection_set(0)
        self.pane._move(-1)
        self.assertEqual([m.name for m in self.pane.get_messages()], ["A01", "A02", "A03"])

    def test_move_does_not_wrap_around_at_end(self) -> None:
        self.pane.listbox.selection_set(2)
        self.pane._move(1)
        self.assertEqual([m.name for m in self.pane.get_messages()], ["A01", "A02", "A03"])


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


@unittest.skipUnless(_tk_available(), "requires a Tk display")
class TestEditorPaneNewMessage(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()
        self.pane = EditorPane(self.root, on_change=lambda: None)
        self.pane.set_messages([
            Message(name="Message 1", format="hl7", content="Content 1"),
            Message(name="Message 2", format="hl7", content="Content 2"),
        ])
        self.pane._refresh_listbox()

    def tearDown(self) -> None:
        self.root.destroy()
        gc.collect()

    def test_new_message_is_appended_with_correct_name(self) -> None:
        self.pane._new_message()
        messages = self.pane.get_messages()
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[2].name, "Message 3")
        self.assertEqual(messages[2].format, "hl7")
        self.assertEqual(messages[2].content, "")

    def test_new_message_is_selected_after_creation(self) -> None:
        self.pane._new_message()
        self.assertEqual(self.pane.listbox.curselection(), (2,))
        self.assertEqual(self.pane._selected_index, 2)

    def test_new_message_content_is_loaded_into_editor(self) -> None:
        self.pane._new_message()
        editor_content = self.pane.text.get("1.0", tk.END).rstrip()
        self.assertEqual(editor_content, "")

    def test_typing_in_new_message_does_not_overwrite_others(self) -> None:
        self.pane._new_message()
        # Simulate typing in the new message
        self.pane._suspend_events = False
        self.pane.text.configure(state="normal")
        self.pane.text.delete("1.0", tk.END)
        self.pane.text.insert("1.0", "New content")
        self.pane.text.edit_modified(True)
        self.pane._commit_current_edits()
        # Verify the new message has the content
        messages = self.pane.get_messages()
        self.assertEqual(messages[2].content, "New content")
        
        # Verify existing messages are unchanged
        self.assertEqual(messages[0].content, "Content 1")
        self.assertEqual(messages[1].content, "Content 2")

    def test_multiple_new_messages_are_added_correctly(self) -> None:
        self.pane._new_message()
        self.pane._new_message()
        self.pane._new_message()
        
        messages = self.pane.get_messages()
        self.assertEqual(len(messages), 5)
        self.assertEqual([m.name for m in messages], [
            "Message 1", "Message 2", "Message 3", "Message 4", "Message 5"
        ])


if __name__ == "__main__":
    unittest.main()
