import gc
import queue
import tkinter as tk
import unittest
from unittest.mock import patch

from ultra7.models import Endpoint, Message
from ultra7.senders.base import SendResult
from ultra7.ui.send_controls import SendControls


def _tk_available() -> bool:
    try:
        root = tk.Tk()
    except tk.TclError:
        return False
    root.destroy()
    return True


@unittest.skipUnless(_tk_available(), "requires a Tk display")
class TestSendWorkerLabels(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()
        self._selected_messages: list[Message] = []
        self.controls = SendControls(
            self.root,
            get_endpoint=lambda: Endpoint(kind="mllp", host="127.0.0.1", port=1),
            get_messages=lambda: [],
            get_selected_messages=lambda: self._selected_messages,
            on_result=lambda *_a: None,
            on_info=lambda *_a: None,
        )

    def tearDown(self) -> None:
        self.root.destroy()
        # Finalize any leftover Tk Variable objects on this (main) thread now,
        # instead of leaving them for the GC to collect on some other thread later.
        gc.collect()

    def _drain(self) -> list[tuple[str | None, SendResult | None]]:
        items = []
        try:
            while True:
                items.append(self.controls._queue.get_nowait())
        except queue.Empty:
            pass
        return items

    def test_repeat_send_labels_include_iteration_count(self) -> None:
        fake_sender = type("FakeSender", (), {"send": lambda self, endpoint, message: SendResult(
            ok=True, latency_ms=1.0, response_summary="ack"
        )})()
        endpoint = Endpoint(kind="mllp", host="127.0.0.1", port=1)
        messages = [Message(name="A01", format="hl7", content="MSH|...")]

        with patch("ultra7.ui.send_controls.get_sender", return_value=fake_sender):
            self.controls._send_worker(endpoint, messages, repeat_count=3, delay_ms=0)

        items = self._drain()
        labels = [name for name, result in items if result is not None]
        self.assertEqual(labels, ["A01 [1/3]", "A01 [2/3]", "A01 [3/3]"])
        self.assertEqual(items[-1], (None, None))  # sentinel marks the job as finished

    def test_send_emits_info_line_with_destination_before_each_send(self) -> None:
        fake_sender = type("FakeSender", (), {"send": lambda self, endpoint, message: SendResult(
            ok=True, latency_ms=1.0, response_summary="ack"
        )})()
        endpoint = Endpoint(kind="mllp", host="127.0.0.1", port=2575)
        messages = [Message(name="A01", format="hl7", content="MSH|...")]

        with patch("ultra7.ui.send_controls.get_sender", return_value=fake_sender):
            self.controls._send_worker(endpoint, messages, repeat_count=2, delay_ms=0)

        items = self._drain()
        info_lines = [name for name, result in items if result is None and name is not None]
        self.assertEqual(
            info_lines,
            [
                "Sending A01 [1/2] to 127.0.0.1 on port 2575",
                "Sending A01 [2/2] to 127.0.0.1 on port 2575",
            ],
        )
        # Each info line is immediately followed by its matching result.
        names_in_order = [name for name, _result in items if name is not None]
        self.assertEqual(
            names_in_order,
            [
                "Sending A01 [1/2] to 127.0.0.1 on port 2575",
                "A01 [1/2]",
                "Sending A01 [2/2] to 127.0.0.1 on port 2575",
                "A01 [2/2]",
            ],
        )

    def test_send_info_line_uses_url_for_rest_endpoint(self) -> None:
        fake_sender = type("FakeSender", (), {"send": lambda self, endpoint, message: SendResult(
            ok=True, latency_ms=1.0, response_summary="ack"
        )})()
        endpoint = Endpoint(kind="rest", url="http://example.test:9090/ingest")
        messages = [Message(name="A01", format="json", content="{}")]

        with patch("ultra7.ui.send_controls.get_sender", return_value=fake_sender):
            self.controls._send_worker(endpoint, messages, repeat_count=1, delay_ms=0)

        items = self._drain()
        info_lines = [name for name, result in items if result is None and name is not None]
        self.assertEqual(info_lines, ["Sending A01 [1/1] to example.test on port 9090"])

    def test_send_once_sends_only_the_selected_message(self) -> None:
        fake_sender = type("FakeSender", (), {"send": lambda self, endpoint, message: SendResult(
            ok=True, latency_ms=1.0, response_summary="ack"
        )})()
        self._selected_messages = [Message(name="Selected", format="hl7", content="MSH|...")]

        with patch("ultra7.ui.send_controls.get_sender", return_value=fake_sender):
            self.controls._start_send_once()
            assert self.controls._worker is not None
            self.controls._worker.join(timeout=2)

        items = self._drain()
        names = [name for name, _result in items if name is not None]
        self.assertEqual(
            names,
            [
                "Sending Selected [1/1] to 127.0.0.1 on port 1",
                "Selected [1/1]",
            ],
        )

    def test_send_once_sends_all_selected_messages(self) -> None:
        fake_sender = type("FakeSender", (), {"send": lambda self, endpoint, message: SendResult(
            ok=True, latency_ms=1.0, response_summary="ack"
        )})()
        self._selected_messages = [
            Message(name="First", format="hl7", content="MSH|..."),
            Message(name="Second", format="hl7", content="MSH|..."),
        ]

        with patch("ultra7.ui.send_controls.get_sender", return_value=fake_sender):
            self.controls._start_send_once()
            assert self.controls._worker is not None
            self.controls._worker.join(timeout=2)

        items = self._drain()
        names = [name for name, _result in items if name is not None]
        self.assertEqual(
            names,
            [
                "Sending First [1/1] to 127.0.0.1 on port 1",
                "First [1/1]",
                "Sending Second [1/1] to 127.0.0.1 on port 1",
                "Second [1/1]",
            ],
        )

    def test_send_once_with_no_selection_sets_status(self) -> None:
        self._selected_messages = []
        self.controls._start_send_once()
        self.assertEqual(self.controls._status_var.get(), "No message selected")
        self.assertIsNone(self.controls._worker)

    def test_send_once_sends_disabled_message_regardless(self) -> None:
        fake_sender = type("FakeSender", (), {"send": lambda self, endpoint, message: SendResult(
            ok=True, latency_ms=1.0, response_summary="ack"
        )})()
        self._selected_messages = [Message(name="Disabled", format="hl7", content="MSH|...", enabled=False)]

        with patch("ultra7.ui.send_controls.get_sender", return_value=fake_sender):
            self.controls._start_send_once()
            assert self.controls._worker is not None
            self.controls._worker.join(timeout=2)

        items = self._drain()
        names = [name for name, _result in items if name is not None]
        self.assertEqual(
            names,
            [
                "Sending Disabled [1/1] to 127.0.0.1 on port 1",
                "Disabled [1/1]",
            ],
        )

    def test_start_send_filters_out_disabled_messages(self) -> None:
        fake_sender = type("FakeSender", (), {"send": lambda self, endpoint, message: SendResult(
            ok=True, latency_ms=1.0, response_summary="ack"
        )})()
        messages = [
            Message(name="Enabled", format="hl7", content="MSH|...", enabled=True),
            Message(name="Disabled", format="hl7", content="MSH|...", enabled=False),
        ]
        self.controls._get_messages = lambda: messages

        with patch("ultra7.ui.send_controls.get_sender", return_value=fake_sender):
            self.controls._start_send()
            assert self.controls._worker is not None
            self.controls._worker.join(timeout=2)

        items = self._drain()
        names = [name for name, _result in items if name is not None]
        self.assertEqual(
            names,
            [
                "Sending Enabled [1/1] to 127.0.0.1 on port 1",
                "Enabled [1/1]",
            ],
        )

    def test_start_send_with_only_disabled_messages_sets_status(self) -> None:
        self.controls._get_messages = lambda: [Message(name="Disabled", format="hl7", content="x", enabled=False)]
        self.controls._start_send()
        self.assertEqual(self.controls._status_var.get(), "No enabled messages to send")
        self.assertIsNone(self.controls._worker)


if __name__ == "__main__":
    unittest.main()
