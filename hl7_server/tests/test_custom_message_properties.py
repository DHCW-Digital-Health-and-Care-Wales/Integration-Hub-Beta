import unittest
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

from hl7apy.core import Message

from hl7_server.custom_message_properties import build_common_properties, build_mpi_properties


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
            self.assertEqual(props["UpdateSource"], "108")
            self.assertEqual(props["AssigningAuthority"], "NHS")
            self.assertEqual(props["DateDeath"], "2023-01-15")
            self.assertEqual(props["ReasonDeath"], "")

            self.assertNotIn("MessageReceivedAt", props)
            self.assertNotIn("CorrelationId", props)
            self.assertNotIn("WorkflowID", props)
            self.assertNotIn("SourceSystem", props)


if __name__ == "__main__":
    unittest.main()
