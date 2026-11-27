import gc
import json
import random
import socket
import time
import tkinter as tk
import unittest

from ultra7.anonymise import anonymise_message
from ultra7.formats.hl7_dictionary import describe_hl7
from ultra7.iteration import apply_iteration, apply_iterations
from ultra7.mock_receiver import MockHttpServer, MockMllpServer, ReceivedMessage
from ultra7.models import Endpoint, IterationSpec, Message
from ultra7.nhs_number import generate_nhs_number, is_valid_nhs_number
from ultra7.senders.connectivity import INTEGRATION_HUB_PRESETS, test_endpoint_connection
from ultra7.senders.mllp_sender import MllpSender
from ultra7.senders.rest_sender import RestSender
from ultra7.ui.diff_dialog import compute_side_by_side_diff
from ultra7.ui.endpoint_dialog import EndpointDialog
from ultra7.ui.iteration_dialog import IterationDialog


def _tk_available() -> bool:
    try:
        root = tk.Tk()
    except tk.TclError:
        return False
    root.destroy()
    return True


class TestHl7Dictionary(unittest.TestCase):
    def test_describes_segments_fields_components_and_repetitions(self) -> None:
        self.assertEqual(describe_hl7("MSH"), "Message Header")
        self.assertEqual(describe_hl7("MSH-10"), "Message Control ID")
        self.assertEqual(describe_hl7("PID-5.2"), "Given Name")
        self.assertEqual(describe_hl7("PID-3[2].1"), "ID Number")
        self.assertEqual(describe_hl7("ZZZ-99"), "")


class TestNhsNumber(unittest.TestCase):
    def test_validates_known_nhs_numbers(self) -> None:
        self.assertTrue(is_valid_nhs_number("943 476 5919"))
        self.assertTrue(is_valid_nhs_number("9434765919"))
        self.assertFalse(is_valid_nhs_number("9434765910"))
        self.assertFalse(is_valid_nhs_number("12345"))

    def test_generates_valid_synthetic_mod11_numbers(self) -> None:
        rng = random.Random(123)  # nosec B311
        for _ in range(50):
            num = generate_nhs_number(rng)
            self.assertEqual(len(num), 10)
            self.assertTrue(num.startswith("999"))
            self.assertTrue(is_valid_nhs_number(num))

        spaced = generate_nhs_number(rng, spaced=True)
        self.assertRegex(spaced, r"^999 \d{3} \d{4}$")
        self.assertTrue(is_valid_nhs_number(spaced))


class TestMultiIteration(unittest.TestCase):
    def test_nhs_number_iteration_mode(self) -> None:
        content = "PID|1||1234567890^^^NHS^NH"
        start = content.index("1234567890")
        spec = IterationSpec(start=start, end=start + 10, mode="nhs_number")
        out = apply_iteration(content, spec, 0, rng=random.Random(7))  # nosec B311
        generated = out[start : start + 10]
        self.assertNotEqual(generated, "1234567890")
        self.assertTrue(is_valid_nhs_number(generated))

    def test_apply_multiple_iterations_right_to_left(self) -> None:
        content = "MSH|^~\\&|APP|FAC|MPI|DHCW|20250101||ADT^A01|0001|P|2.5\nPID|1||1234567890^^^NHS^NH||SMITH^JANE"
        id_start = content.index("0001")
        nhs_start = content.index("1234567890")
        name_start = content.index("JANE")
        specs = [
            IterationSpec(start=id_start, end=id_start + 4, mode="increment", step=1),
            IterationSpec(start=nhs_start, end=nhs_start + 10, mode="nhs_number"),
            IterationSpec(start=name_start, end=name_start + 4, mode="list", values=["ALICE", "BOB"]),
        ]
        rendered = apply_iterations(content, specs, iteration_index=1, rng=random.Random(99))  # nosec B311
        self.assertIn("|0002|", rendered)
        self.assertIn("SMITH^BOB", rendered)
        pid_id = rendered.split("PID|1||", 1)[1][:10]
        self.assertTrue(is_valid_nhs_number(pid_id))

    def test_message_multi_iteration_round_trip(self) -> None:
        s1 = IterationSpec(start=0, end=4, mode="increment", step=2)
        s2 = IterationSpec(start=10, end=20, mode="nhs_number")
        msg = Message(name="Multi", format="hl7", content="0001------1234567890", iterations=[s1, s2])
        restored = Message.from_dict(msg.to_dict())
        self.assertEqual(len(restored.all_iterations()), 2)
        self.assertEqual(restored.iteration, s1)
        self.assertEqual(restored.iterations[1].mode, "nhs_number")


class TestAnonymise(unittest.TestCase):
    def test_anonymises_hl7_pii_while_preserving_structure(self) -> None:
        hl7 = (
            "MSH|^~\\&|PHW|SITE|MPI|DHCW|20250101||ADT^A01|CTL1|P|2.5\r"
            "PID|1||9434765919^^^NHS^NH||JONES^SARAH||19820415|F|||99 REAL ST^^LONDON^^SW1A 1AA||07123456789"
        )
        scrubbed = anonymise_message(hl7, "hl7", seed=1)
        self.assertIn("MSH|^~\\&|PHW|SITE|MPI|DHCW|20250101||ADT^A01|CTL1|P|2.5\r", scrubbed)
        self.assertNotIn("JONES^SARAH", scrubbed)
        self.assertNotIn("9434765919", scrubbed)
        self.assertNotIn("99 REAL ST", scrubbed)
        self.assertNotIn("07123456789", scrubbed)
        pid_fields = scrubbed.split("\r")[1].split("|")
        new_nhs = pid_fields[3].split("^")[0]
        self.assertTrue(is_valid_nhs_number(new_nhs))
        self.assertTrue(pid_fields[3].endswith("^^^NHS^NH"))

    def test_anonymises_xml_pii(self) -> None:
        xml = (
            '<Patient>'
            '<NHSNumber value="9434765919"/>'
            '<Surname><![CDATA[RealName]]></Surname>'
            '<GivenName>RealGiven</GivenName>'
            '<Code>KEEP</Code>'
            '</Patient>'
        )
        scrubbed = anonymise_message(xml, "xml", seed=2)
        self.assertNotIn("9434765919", scrubbed)
        self.assertNotIn("RealName", scrubbed)
        self.assertNotIn("RealGiven", scrubbed)
        self.assertIn("<![CDATA[", scrubbed)
        self.assertIn("<Code>KEEP</Code>", scrubbed)

    def test_anonymises_hl7_nk1_and_mrg_repetitions(self) -> None:
        hl7 = (
            "MSH|^~\\&|PHW|SITE|MPI|DHCW|20250101||ADT^A40|CTL1|P|2.5\r"
            "NK1|1|PATEL^PRIYA~BAKER^TOM|SPO|"
            "1 REAL RD^^CARDIFF^^CF10 1ZZ~2 REAL AVE^^SWANSEA^^SA1 1ZZ|07111111111~07222222222\r"
            "MRG|9434765919^^^NHS^NH||||||OLDONE^FIRST~OLDTWO^SECOND"
        )
        scrubbed = anonymise_message(hl7, "hl7", seed=4)
        leaked_values = (
            "PATEL",
            "PRIYA",
            "BAKER",
            "TOM",
            "1 REAL RD",
            "2 REAL AVE",
            "07111111111",
            "07222222222",
            "OLDONE",
            "OLDTWO",
        )
        for leaked in leaked_values:
            self.assertNotIn(leaked, scrubbed)

    def test_anonymises_json_fhir_patient(self) -> None:
        payload = json.dumps({
            "resourceType": "Patient",
            "identifier": [{"system": "https://fhir.nhs.uk/Id/nhs-number", "value": "9434765919"}],
            "name": [{"family": "RealFamily", "given": ["RealGiven"]}],
            "telecom": [
                {"system": "phone", "value": "07123456789"},
                {"system": "email", "value": "real.person@nhs.wales"},
            ],
            "birthDate": "1970-01-01",
        })
        scrubbed = json.loads(anonymise_message(payload, "json", seed=3))
        self.assertEqual(scrubbed["resourceType"], "Patient")
        self.assertNotEqual(scrubbed["name"][0]["family"], "RealFamily")
        self.assertTrue(is_valid_nhs_number(scrubbed["identifier"][0]["value"]))
        self.assertNotEqual(scrubbed["telecom"][0]["value"], "07123456789")
        self.assertEqual(scrubbed["telecom"][1]["value"], "test.patient@example.test")


class TestSideBySideDiff(unittest.TestCase):
    def test_computes_added_removed_and_changed_lines(self) -> None:
        left = "MSH|1\nPID|OLD\nPV1|ONLY_LEFT"
        right = "MSH|1\nPID|NEW\nOBX|ONLY_RIGHT"
        l_rows, r_rows, added, removed = compute_side_by_side_diff(left, right)
        self.assertEqual(len(l_rows), len(r_rows))
        self.assertEqual(l_rows[0], ("MSH|1", ""))
        self.assertGreaterEqual(added, 1)
        self.assertGreaterEqual(removed, 1)


class TestMockReceiversAndConnectivity(unittest.TestCase):
    def test_mock_mllp_receiver_and_connectivity_check(self) -> None:
        captured: list[ReceivedMessage] = []
        server = MockMllpServer("127.0.0.1", 0, ack_code="AA", on_message=captured.append)
        port = server.start()
        try:
            endpoint = Endpoint(kind="mllp", host="127.0.0.1", port=port, timeout_seconds=2.0)
            ok, latency, detail = test_endpoint_connection(endpoint)
            self.assertTrue(ok, detail)
            self.assertGreaterEqual(latency, 0.0)

            msg = Message(name="A01", format="hl7", content="MSH|^~\\&|A|B|C|D|2025||ADT^A01|MSG42|P|2.5")
            result = MllpSender().send(endpoint, msg)
            self.assertTrue(result.ok, result.error)
            self.assertIn("MSA|AA|MSG42", result.response_summary)
            self.assertEqual(len(captured), 1)
            self.assertIn("MSG42", captured[0].content)
        finally:
            server.stop()

    def test_mock_http_receiver_and_connectivity_check(self) -> None:
        captured: list[ReceivedMessage] = []
        server = MockHttpServer(
            "127.0.0.1", 0, status_code=201, response_body='{"accepted": true}', on_message=captured.append
        )
        port = server.start()
        try:
            endpoint = Endpoint(kind="rest", url=f"http://127.0.0.1:{port}/ingest", timeout_seconds=2.0)
            ok, _latency, detail = test_endpoint_connection(endpoint)
            self.assertTrue(ok, detail)

            msg = Message(name="J1", format="json", content='{"hello": "world"}')
            result = RestSender().send(endpoint, msg)
            self.assertTrue(result.ok, result.error)
            self.assertIn("HTTP 201", result.response_summary)
            self.assertEqual(len(captured), 1)
            self.assertEqual(captured[0].detected_format, "json")
        finally:
            server.stop()

    def test_integration_hub_presets_exist(self) -> None:
        self.assertGreaterEqual(len(INTEGRATION_HUB_PRESETS), 5)

    def test_malformed_url_returns_error_instead_of_raising(self) -> None:
        ok, _latency, detail = test_endpoint_connection(Endpoint(kind="rest", url="http://[::1"))
        self.assertFalse(ok)
        self.assertTrue(detail)

    def test_mock_http_receiver_captures_even_when_client_disconnects_during_delay(self) -> None:
        captured: list[ReceivedMessage] = []
        server = MockHttpServer("127.0.0.1", 0, delay_ms=150, on_message=captured.append)
        port = server.start()
        try:
            body = b'{"timeout": true}'
            raw_req = (
                f"POST /ingest HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
                f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n"
            ).encode("ascii") + body
            with socket.create_connection(("127.0.0.1", port), timeout=1.0) as sock:
                sock.sendall(raw_req)
            # Socket closed immediately before delay_ms elapses; wait for handler to finish.
            deadline = time.monotonic() + 2.0
            while not captured and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertEqual(len(captured), 1)
            self.assertIn("timeout", captured[0].content)
        finally:
            server.stop()

    def test_mllp_persistent_stream_reuses_single_tcp_connection(self) -> None:
        captured: list[ReceivedMessage] = []
        server = MockMllpServer("127.0.0.1", 0, ack_code="AA", on_message=captured.append)
        port = server.start()
        try:
            endpoint = Endpoint(kind="mllp", host="127.0.0.1", port=port, timeout_seconds=2.0, mllp_mode="stream")
            self.assertEqual(Endpoint.from_dict(endpoint.to_dict()).mllp_mode, "stream")

            sender = MllpSender()
            with sender.open_stream(endpoint) as session:
                for idx in range(1, 5):
                    msg = Message(
                        name=f"M{idx}",
                        format="hl7",
                        content=f"MSH|^~\\&|A|B|C|D|2025||ADT^A01|CTL{idx:03d}|P|2.5",
                    )
                    result = session.send_message(msg)
                    self.assertTrue(result.ok, result.error)
                    self.assertIn(f"MSA|AA|CTL{idx:03d}", result.response_summary)

            self.assertEqual(len(captured), 4)
            # All 4 messages arrived on the exact same client TCP socket (same ephemeral port).
            self.assertEqual(len({m.remote for m in captured}), 1)
        finally:
            server.stop()

    def test_mllp_pipelined_frames_share_one_stream_and_return_ordered_acks(self) -> None:
        captured: list[ReceivedMessage] = []
        server = MockMllpServer("127.0.0.1", 0, ack_code="AA", on_message=captured.append)
        port = server.start()
        try:
            endpoint = Endpoint(kind="mllp", host="127.0.0.1", port=port, timeout_seconds=2.0, mllp_mode="pipelined")
            sender = MllpSender()
            with sender.open_stream(endpoint) as session:
                for idx in range(1, 6):
                    session.send_frame(
                        Message(
                            name=f"P{idx}",
                            format="hl7",
                            content=f"MSH|^~\\&|A|B|C|D|2025||ADT^A01|PIPE{idx:02d}|P|2.5",
                        )
                    )
                acks = [session.read_next_ack() for _ in range(5)]

            self.assertTrue(all(r.ok for r in acks))
            for idx, res in enumerate(acks, start=1):
                self.assertIn(f"MSA|AA|PIPE{idx:02d}", res.response_summary)
            self.assertEqual(len(captured), 5)
            self.assertEqual(len({m.remote for m in captured}), 1)
        finally:
            server.stop()


class TestEndpointIsConfigured(unittest.TestCase):
    def test_mllp_rest_and_soap_configured_checks(self) -> None:
        self.assertFalse(Endpoint(kind="mllp").is_configured)
        self.assertFalse(Endpoint(kind="mllp", host="127.0.0.1", port=None).is_configured)
        self.assertFalse(Endpoint(kind="mllp", host="", port=2575).is_configured)
        self.assertFalse(Endpoint(kind="mllp", host="127.0.0.1", port=0).is_configured)
        self.assertFalse(Endpoint(kind="mllp", host="127.0.0.1", port=70000).is_configured)
        self.assertTrue(Endpoint(kind="mllp", host="127.0.0.1", port=2575).is_configured)

        self.assertFalse(Endpoint(kind="rest", url="").is_configured)
        self.assertFalse(Endpoint(kind="rest", url="http://").is_configured)
        self.assertFalse(Endpoint(kind="rest", url="ftp://example.test/api").is_configured)
        self.assertTrue(Endpoint(kind="rest", url="http://127.0.0.1:8080/ingest").is_configured)
        self.assertTrue(Endpoint(kind="soap", url="https://example.test/soap").is_configured)

        # Every built-in Integration Hub preset must be configured and include MLLP, REST, and SOAP.
        kinds = {ep.kind for _label, ep in INTEGRATION_HUB_PRESETS}
        self.assertTrue({"mllp", "rest", "soap"}.issubset(kinds))
        for label, ep in INTEGRATION_HUB_PRESETS:
            self.assertTrue(ep.is_configured, f"Preset {label!r} should be configured")


@unittest.skipUnless(_tk_available(), "requires a Tk display")
class TestIterationAndEndpointDialogs(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self) -> None:
        self.root.destroy()
        gc.collect()

    def test_iteration_dialog_live_preview_and_validation(self) -> None:
        # Numeric text defaults to increment and renders live #1..#3 preview
        dlg_num = IterationDialog(self.root, 0, 4, "0001")
        self.assertEqual(dlg_num._current_mode(), "increment")
        self.assertIn("#1: 0001", dlg_num._preview_var.get())
        self.assertIn("#2: 0002", dlg_num._preview_var.get())
        self.assertIn("#3: 0003", dlg_num._preview_var.get())
        dlg_num._save()
        self.assertIsNotNone(dlg_num.result)
        assert dlg_num.result is not None
        self.assertEqual(dlg_num.result.mode, "increment")

        # Non-numeric text defaults to list; switching to increment shows warning and blocks Save
        dlg_txt = IterationDialog(self.root, 0, 4, "JANE")
        self.assertEqual(dlg_txt._current_mode(), "list")
        dlg_txt._mode_label.set("Increment integer (add step each repeat)")
        dlg_txt._on_mode_change()
        self.assertIn("not an integer", dlg_txt._warning_var.get())
        dlg_txt._save()
        self.assertIsNone(dlg_txt.result)
        self.assertTrue(dlg_txt.winfo_exists())
        dlg_txt.destroy()

    def test_endpoint_dialog_validates_and_applies_presets(self) -> None:
        dlg = EndpointDialog(self.root, Endpoint(kind="mllp"))
        # Saving an unconfigured MLLP endpoint should display an error and stay open
        dlg._save()
        self.assertIsNone(dlg.result)
        self.assertIn("Host is required", dlg._error_var.get())
        self.assertTrue(dlg.winfo_exists())

        # Invalid REST URL rejected
        dlg._kind_label.set("REST (HTTP / HTTPS POST)")
        dlg._on_kind_change()
        dlg._url.set("not-a-url")
        dlg._save()
        self.assertIsNone(dlg.result)
        self.assertIn("http://", dlg._error_var.get())

        # Applying a REST preset populates valid fields and saves cleanly
        rest_preset_name = next(label for label, ep in INTEGRATION_HUB_PRESETS if ep.kind == "rest")
        dlg._apply_preset(rest_preset_name)
        dlg._save()
        self.assertIsNotNone(dlg.result)
        assert dlg.result is not None
        self.assertEqual(dlg.result.kind, "rest")
        self.assertTrue(dlg.result.is_configured)


if __name__ == "__main__":
    unittest.main()
