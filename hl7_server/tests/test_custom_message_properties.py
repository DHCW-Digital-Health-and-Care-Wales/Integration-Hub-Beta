import unittest
import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from hl7apy.core import Message

from hl7_server.custom_message_properties import build_common_properties, build_mpi_properties


def _rep_with_hd1(code: str) -> SimpleNamespace:
    # Mimics rep.cx_4.hd_1.value.value expected by production code
    return SimpleNamespace(
        cx_4=SimpleNamespace(
            hd_1=SimpleNamespace(
                value=SimpleNamespace(value=code)
            )
        )
    )

class TestCustomMessageProperties(unittest.TestCase):
    def test_build_common_properties_contains_all_fields(self) -> None:
        workflow_id = "test-workflow"
        sending_app = "252"

        props = build_common_properties(workflow_id, sending_app)

        self.assertIn("MessageReceivedAt", props)
        self.assertIn("CorrelationId", props)
        self.assertEqual(props["WorkflowID"], workflow_id)
        self.assertEqual(props["SourceSystem"], sending_app)

    def test_build_common_properties_with_none_sending_app(self) -> None:
        workflow_id = "test-workflow"
        sending_app = None

        props = build_common_properties(workflow_id, sending_app)

        self.assertEqual(props["SourceSystem"], "")

    def test_build_common_properties_message_received_at_is_iso_format(self) -> None:
        workflow_id = "test-workflow"
        sending_app = "252"

        props = build_common_properties(workflow_id, sending_app)

        try:
            datetime.fromisoformat(props["MessageReceivedAt"].replace("Z", "+00:00"))
        except ValueError:
            self.fail("MessageReceivedAt is not in valid ISO format")

    def test_build_common_properties_correlation_id_is_valid_uuid(self) -> None:
        workflow_id = "test-workflow"
        sending_app = "252"

        props = build_common_properties(workflow_id, sending_app)

        try:
            uuid.UUID(props["CorrelationId"])
        except ValueError:
            self.fail("CorrelationId is not a valid UUID")

    def test_build_mpi_properties_returns_flow_specific_properties_only(self) -> None:
        mock_msg = MagicMock(spec=Message)

        with patch("hl7_server.custom_message_properties.get_hl7_field_value") as mock_get_field:
            mock_get_field.side_effect = lambda msg, path: {
                "msh.msh_9.msh_9_2": "A28",
                "pid.pid_2.cx_4.hd_1": "108",
                "pid.pid_3.cx_4.hd_1": "NHS",
                "pid.pid_29.ts_1": "2023-01-15",
                "pid.pid_30": "",
            }.get(path, "")

            props = build_mpi_properties(mock_msg)

            self.assertEqual(props["MessageType"], "A28")
            self.assertEqual(props["UpdateSources"], "|108|")
            self.assertEqual(props["AssigningAuthorities"], "|NHS|")
            self.assertEqual(props["DateDeath"], "2023-01-15")
            self.assertEqual(props["ReasonDeath"], "")

            self.assertNotIn("MessageReceivedAt", props)
            self.assertNotIn("CorrelationId", props)
            self.assertNotIn("WorkflowID", props)
            self.assertNotIn("SourceSystem", props)

    def test_build_mpi_properties_builds_update_sources_from_pid2_repetitions(self) -> None:
        mock_msg = MagicMock(spec=Message)
        mock_msg.pid = SimpleNamespace(
            pid_2=[_rep_with_hd1("108"), _rep_with_hd1("252"), _rep_with_hd1("999")],
            pid_3=[]
        )

        with patch("hl7_server.custom_message_properties.get_hl7_field_value") as mock_get_field:
            mock_get_field.side_effect = lambda msg, path: {
                "msh.msh_9.msh_9_2": "A28",
                "pid.pid_2.cx_4.hd_1": "108",
                "pid.pid_3.cx_4.hd_1": "NHS",
                "pid.pid_29.ts_1": "",
                "pid.pid_30": "",
            }.get(path, "")

            props = build_mpi_properties(mock_msg)

        self.assertEqual(props["UpdateSources"], "|108|252|999|")

    def test_build_mpi_properties_builds_assigning_authorities_from_pid3_repetitions(self) -> None:
        mock_msg = MagicMock(spec=Message)
        mock_msg.pid = SimpleNamespace(
            pid_2=[],
            pid_3=[_rep_with_hd1("NHS"), _rep_with_hd1("PAS"), _rep_with_hd1("LIS")]
        )

        with patch("hl7_server.custom_message_properties.get_hl7_field_value") as mock_get_field:
            mock_get_field.side_effect = lambda msg, path: {
                "msh.msh_9.msh_9_2": "A28",
                "pid.pid_2.cx_4.hd_1": "108",
                "pid.pid_3.cx_4.hd_1": "NHS",
                "pid.pid_29.ts_1": "",
                "pid.pid_30": "",
            }.get(path, "")

            props = build_mpi_properties(mock_msg)

        self.assertEqual(props["AssigningAuthorities"], "|NHS|PAS|LIS|")

    def test_build_mpi_properties_deduplicates_update_sources_and_assigning_authorities(self) -> None:
        mock_msg = MagicMock(spec=Message)
        mock_msg.pid = SimpleNamespace(
            pid_2=[_rep_with_hd1("108"), _rep_with_hd1("108"), _rep_with_hd1("252")],
            pid_3=[_rep_with_hd1("NHS"), _rep_with_hd1("NHS"), _rep_with_hd1("PAS")]
        )

        with patch("hl7_server.custom_message_properties.get_hl7_field_value") as mock_get_field:
            mock_get_field.side_effect = lambda msg, path: {
                "msh.msh_9.msh_9_2": "A28",
                "pid.pid_2.cx_4.hd_1": "108",
                "pid.pid_3.cx_4.hd_1": "NHS",
                "pid.pid_29.ts_1": "",
                "pid.pid_30": "",
            }.get(path, "")

            props = build_mpi_properties(mock_msg)

            self.assertEqual(props["UpdateSources"], "|108|252|")
            self.assertEqual(props["AssigningAuthorities"], "|NHS|PAS|")

    def test_build_mpi_properties_empty_lists_when_no_pid_repetitions(self) -> None:
        mock_msg = MagicMock(spec=Message)
        mock_msg.pid = SimpleNamespace(pid_2=None, pid_3=None)

        with patch("hl7_server.custom_message_properties.get_hl7_field_value") as mock_get_field:
            mock_get_field.side_effect = lambda msg, path: {
                "msh.msh_9.msh_9_2": "A28",
                "pid.pid_2.cx_4.hd_1": "",
                "pid.pid_3.cx_4.hd_1": "",
                "pid.pid_29.ts_1": "",
                "pid.pid_30": "",
            }.get(path, "")

            props = build_mpi_properties(mock_msg)

            self.assertEqual(props["UpdateSources"], "")
            self.assertEqual(props["AssigningAuthorities"], "")

    def test_build_mpi_properties_single_update_source(self) -> None:
        mock_msg = MagicMock(spec=Message)
        mock_msg.pid = SimpleNamespace(
            pid_2=[_rep_with_hd1("108")],
            pid_3=[]
        )

        with patch("hl7_server.custom_message_properties.get_hl7_field_value") as mock_get_field:
            mock_get_field.side_effect = lambda msg, path: {
                "msh.msh_9.msh_9_2": "A28",
                "pid.pid_2.cx_4.hd_1": "108",
                "pid.pid_3.cx_4.hd_1": "",
                "pid.pid_29.ts_1": "",
                "pid.pid_30": "",
            }.get(path, "")

            props = build_mpi_properties(mock_msg)

            self.assertEqual(props["UpdateSources"], "|108|")

    def test_build_mpi_properties_single_assigning_authority(self) -> None:
        mock_msg = MagicMock(spec=Message)
        mock_msg.pid = SimpleNamespace(
            pid_2=[],
            pid_3=[_rep_with_hd1("NHS")]
        )

        with patch("hl7_server.custom_message_properties.get_hl7_field_value") as mock_get_field:
            mock_get_field.side_effect = lambda msg, path: {
                "msh.msh_9.msh_9_2": "A28",
                "pid.pid_2.cx_4.hd_1": "",
                "pid.pid_3.cx_4.hd_1": "NHS",
                "pid.pid_29.ts_1": "",
                "pid.pid_30": "",
            }.get(path, "")

            props = build_mpi_properties(mock_msg)

            self.assertEqual(props["AssigningAuthorities"], "|NHS|")

if __name__ == "__main__":
    unittest.main()
