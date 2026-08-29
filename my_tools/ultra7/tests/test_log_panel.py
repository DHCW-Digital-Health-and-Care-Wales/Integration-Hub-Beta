import gc
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import filedialog
from unittest.mock import patch

from ultra7.senders.base import SendResult
from ultra7.ui.log_panel import LogPanel


def _tk_available() -> bool:
    try:
        root = tk.Tk()
    except tk.TclError:
        return False
    root.destroy()
    return True


@unittest.skipUnless(_tk_available(), "requires a Tk display")
class TestLogPanel(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()
        self.panel = LogPanel(self.root)

    def tearDown(self) -> None:
        self.root.destroy()
        # Finalize any leftover Tk Variable objects on this (main) thread now,
        # instead of leaving them for the GC to collect on some other thread later.
        gc.collect()

    def test_append_includes_millisecond_timestamp(self) -> None:
        self.panel.append("A01", SendResult(ok=True, latency_ms=12.3, response_summary="ack"))
        line = self.panel.text.get("1.0", "end-1c")
        self.assertRegex(line, r"^\[\d{2}:\d{2}:\d{2}\.\d{3}\] A01")

    def test_blank_line_separates_consecutive_entries(self) -> None:
        self.panel.append("A01", SendResult(ok=True, latency_ms=1.0, response_summary="ack"))
        self.panel.append("A02", SendResult(ok=True, latency_ms=1.0, response_summary="ack"))
        content = self.panel.text.get("1.0", "end-1c")
        lines = content.split("\n")
        self.assertIn("A01", lines[0])
        self.assertEqual(lines[1], "")
        self.assertIn("A02", lines[2])

    def test_append_info_includes_text_and_timestamp(self) -> None:
        self.panel.append_info("Sending A01 [1/5] to 127.0.0.1 on port 2575")
        line = self.panel.text.get("1.0", "end-1c")
        self.assertRegex(line, r"^\[\d{2}:\d{2}:\d{2}\.\d{3}\] Sending A01 \[1/5\] to 127\.0\.0\.1 on port 2575$")

    def test_result_stays_directly_under_its_info_line(self) -> None:
        self.panel.append_info("Sending A01 [1/1] to 127.0.0.1 on port 2575")
        self.panel.append("A01 [1/1]", SendResult(ok=True, latency_ms=1.0, response_summary="ack"))
        content = self.panel.text.get("1.0", "end-1c")
        lines = content.split("\n")
        self.assertIn("Sending A01", lines[0])
        self.assertIn("A01 [1/1] —", lines[1])  # no blank line between info and its result

    def test_blank_line_separates_info_blocks(self) -> None:
        self.panel.append_info("Sending A01 [1/2] to 127.0.0.1 on port 2575")
        self.panel.append("A01 [1/2]", SendResult(ok=True, latency_ms=1.0, response_summary="ack"))
        self.panel.append_info("Sending A01 [2/2] to 127.0.0.1 on port 2575")
        content = self.panel.text.get("1.0", "end-1c")
        lines = content.split("\n")
        self.assertEqual(lines[2], "")  # blank line before the second block's info line
        self.assertIn("Sending A01 [2/2]", lines[3])

    def test_clear_empties_log(self) -> None:
        self.panel.append("A01", SendResult(ok=True, latency_ms=1.0, response_summary="ack"))
        self.panel.clear()
        self.assertEqual(self.panel.text.get("1.0", "end-1c"), "")

    def test_save_to_disk_writes_log_contents(self) -> None:
        self.panel.append("A01", SendResult(ok=True, latency_ms=1.0, response_summary="ack"))
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "ultra7.log")
            with patch.object(filedialog, "asksaveasfilename", return_value=path):
                self.panel.save_to_disk()
            content = Path(path).read_text(encoding="utf-8")
        self.assertIn("A01", content)

    def test_save_to_disk_cancelled_dialog_is_noop(self) -> None:
        self.panel.append("A01", SendResult(ok=True, latency_ms=1.0, response_summary="ack"))
        with patch.object(filedialog, "asksaveasfilename", return_value=""):
            self.panel.save_to_disk()  # should not raise


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()
