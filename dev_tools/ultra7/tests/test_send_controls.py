import gc
import queue
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from ultra7.mock_receiver import MockMllpServer, ReceivedMessage
from ultra7.models import Endpoint, IterationSpec, Message, Project
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

    def test_each_message_applies_its_own_iteration_spec_per_repeat(self) -> None:
        """Two messages, each with a different iteration mode, batch-sent over 3 repeats:
        every send must use that message's own spec and the shared repeat index, without
        the two messages' iteration state leaking into each other or accumulating."""
        sent_contents: list[str] = []

        def _record_send(_self: object, _endpoint: Endpoint, message: Message) -> SendResult:
            sent_contents.append(message.content)
            return SendResult(ok=True, latency_ms=1.0, response_summary="ack")

        fake_sender = type("FakeSender", (), {"send": _record_send})()

        content_a = "MSH|...|000001|P|2.5"
        start_a = content_a.index("000001")
        message_a = Message(
            name="A01",
            format="hl7",
            content=content_a,
            iteration=IterationSpec(start=start_a, end=start_a + 6, mode="increment", step=1),
        )
        content_b = "PID|1||PATIENT_A"
        start_b = content_b.index("PATIENT_A")
        message_b = Message(
            name="A02",
            format="hl7",
            content=content_b,
            iteration=IterationSpec(
                start=start_b, end=start_b + len("PATIENT_A"), mode="list", values=["PATIENT_A", "PATIENT_B"]
            ),
        )
        endpoint = Endpoint(kind="mllp", host="127.0.0.1", port=1)

        with patch("ultra7.ui.send_controls.get_sender", return_value=fake_sender):
            self.controls._send_worker(endpoint, [message_a, message_b], repeat_count=3, delay_ms=0)

        self.assertEqual(
            sent_contents,
            [
                "MSH|...|000001|P|2.5",
                "PID|1||PATIENT_A",
                "MSH|...|000002|P|2.5",
                "PID|1||PATIENT_B",
                "MSH|...|000003|P|2.5",
                "PID|1||PATIENT_A",  # wraps around
            ],
        )
        # Originals must stay untouched — each send recomputes from the source, not the last output.
        self.assertEqual(message_a.content, content_a)
        self.assertEqual(message_b.content, content_b)

    def test_set_enabled_keeps_cancel_disabled_when_idle(self) -> None:
        self.controls.set_enabled(True)
        self.assertEqual(str(self.controls._send_btn.cget("state")), "normal")
        self.assertEqual(str(self.controls._cancel_btn.cget("state")), "disabled")

    def test_start_batch_runs_projects_and_blocks_concurrent_send(self) -> None:
        fake_sender = type("FakeSender", (), {"send": lambda self, endpoint, message: SendResult(
            ok=True, latency_ms=1.0, response_summary="ack"
        )})()
        projects = [
            Project(
                name="P1",
                endpoint=Endpoint(kind="mllp", host="127.0.0.1", port=2575),
                messages=[Message(name="M1", format="hl7", content="MSH|...")],
            ),
            Project(
                name="P2",
                endpoint=Endpoint(kind="mllp", host="127.0.0.1", port=2576),
                messages=[Message(name="M2", format="hl7", content="MSH|...", enabled=False)],
            ),
        ]

        with patch("ultra7.ui.send_controls.get_sender", return_value=fake_sender):
            started = self.controls.start_batch(projects)
            self.assertTrue(started)
            self.assertFalse(self.controls.start_batch(projects))
            self.assertEqual(str(self.controls._cancel_btn.cget("state")), "normal")
            assert self.controls._worker is not None
            self.controls._worker.join(timeout=2)

        items = self._drain()
        names = [name for name, _result in items if name is not None]
        self.assertEqual(
            names,
            [
                "=== Running: P1 ===",
                "Sending   M1 [1/1] to 127.0.0.1 on port 2575",
                "  M1 [1/1]",
                "=== Running: P2 ===",
                "No enabled messages",
            ],
        )

    def test_cancel_interrupts_delay_promptly(self) -> None:
        fake_sender = type("FakeSender", (), {"send": lambda self, endpoint, message: SendResult(
            ok=True, latency_ms=1.0, response_summary="ack"
        )})()
        self.controls._get_messages = lambda: [Message(name="A01", format="hl7", content="MSH|...")]
        self.controls.set_repeat_and_delay(repeat_count=3, delay_ms=5000)

        start = time.monotonic()
        with patch("ultra7.ui.send_controls.get_sender", return_value=fake_sender):
            self.controls._start_send()
            time.sleep(0.05)
            self.controls._cancel()
            assert self.controls._worker is not None
            self.controls._worker.join(timeout=2)
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 1.0)

    def test_setting_change_triggers_on_change(self) -> None:
        called = False

        def _mark() -> None:
            nonlocal called
            called = True

        controls = SendControls(
            self.root,
            get_endpoint=lambda: Endpoint(),
            get_messages=lambda: [],
            get_selected_messages=lambda: [],
            on_result=lambda *_a: None,
            on_info=lambda *_a: None,
            on_change=_mark,
        )
        controls._handle_setting_change(None)  # type: ignore[arg-type]
        self.assertTrue(called)

    def test_send_worker_mllp_stream_and_pipelined_modes(self) -> None:
        captured: list[ReceivedMessage] = []
        server = MockMllpServer("127.0.0.1", 0, ack_code="AA", on_message=captured.append)
        port = server.start()
        try:
            content = "MSH|^~\\&|A|B|C|D|2025||ADT^A01|0001|P|2.5"
            start = content.index("0001")
            msg = Message(
                name="A01",
                format="hl7",
                content=content,
                iteration=IterationSpec(start=start, end=start + 4, mode="increment", step=1),
            )

            for mode in ("stream", "pipelined"):
                captured.clear()
                endpoint = Endpoint(
                    kind="mllp", host="127.0.0.1", port=port, timeout_seconds=2.0, mllp_mode=mode  # type: ignore[arg-type]
                )
                self.controls._send_worker(endpoint, [msg], repeat_count=3, delay_ms=0)
                items = self._drain()
                results = [res for _name, res in items if res is not None]
                self.assertEqual(len(results), 3)
                self.assertTrue(all(r.ok for r in results))
                self.assertIn("MSA|AA|0001", results[0].response_summary)
                self.assertIn("MSA|AA|0002", results[1].response_summary)
                self.assertIn("MSA|AA|0003", results[2].response_summary)
                self.assertEqual(len(captured), 3)
                self.assertEqual(len({m.remote for m in captured}), 1)
        finally:
            server.stop()

    def test_inline_mllp_mode_selector_syncs_and_notifies(self) -> None:
        changed_modes: list[str] = []
        dirty = False

        def _on_dirty() -> None:
            nonlocal dirty
            dirty = True

        controls = SendControls(
            self.root,
            get_endpoint=lambda: Endpoint(kind="mllp", host="127.0.0.1", port=2575),
            get_messages=lambda: [],
            get_selected_messages=lambda: [],
            on_result=lambda *_a: None,
            on_info=lambda *_a: None,
            on_change=_on_dirty,
            on_mllp_mode_change=changed_modes.append,
        )
        controls.sync_endpoint(Endpoint(kind="mllp", host="127.0.0.1", port=2575, mllp_mode="stream"))
        self.assertEqual(controls._mllp_mode_var.get(), "Stream (1 TCP)")
        self.assertEqual(str(controls._mllp_mode_combo.cget("state")), "readonly")

        controls._mllp_mode_var.set("Pipelined burst")
        controls._handle_mllp_mode_change()
        self.assertEqual(changed_modes, ["pipelined"])
        self.assertTrue(dirty)

        # Disabled automatically for REST / SOAP endpoints
        controls.sync_endpoint(Endpoint(kind="rest", url="http://127.0.0.1:8080/ingest"))
        self.assertEqual(str(controls._mllp_mode_combo.cget("state")), "disabled")

    def test_unconfigured_endpoint_prompts_and_blocks_if_cancelled(self) -> None:
        prompt_calls = 0
        endpoint = Endpoint(kind="mllp", host="", port=None)

        def _prompt() -> bool:
            nonlocal prompt_calls
            prompt_calls += 1
            return False

        controls = SendControls(
            self.root,
            get_endpoint=lambda: endpoint,
            get_messages=lambda: [Message(name="A01", format="hl7", content="MSH|...")],
            get_selected_messages=lambda: [Message(name="A01", format="hl7", content="MSH|...")],
            on_result=lambda *_a: None,
            on_info=lambda *_a: None,
            on_unconfigured_endpoint=_prompt,
        )
        controls._start_send()
        self.assertEqual(prompt_calls, 1)
        self.assertIsNone(controls._worker)
        self.assertEqual(controls._status_var.get(), "Configure an endpoint first")

    def test_unconfigured_endpoint_sends_after_prompt_configures_it(self) -> None:
        fake_sender = type("FakeSender", (), {"send": lambda self, endpoint, message: SendResult(
            ok=True, latency_ms=1.0, response_summary="ack"
        )})()
        endpoint_box = [Endpoint(kind="mllp", host="", port=None)]

        def _configure() -> bool:
            endpoint_box[0] = Endpoint(kind="mllp", host="127.0.0.1", port=2575)
            return True

        controls = SendControls(
            self.root,
            get_endpoint=lambda: endpoint_box[0],
            get_messages=lambda: [Message(name="A01", format="hl7", content="MSH|...")],
            get_selected_messages=lambda: [Message(name="A01", format="hl7", content="MSH|...")],
            on_result=lambda *_a: None,
            on_info=lambda *_a: None,
            on_unconfigured_endpoint=_configure,
        )
        with patch("ultra7.ui.send_controls.get_sender", return_value=fake_sender):
            controls._start_send_once()
            assert controls._worker is not None
            controls._worker.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
