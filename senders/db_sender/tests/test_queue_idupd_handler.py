import unittest
from unittest.mock import MagicMock

from message_bus_lib.dead_letter import DeadLetterMessage

from db_sender.app_config import AppConfig
from db_sender.handlers.queue_idupd_handler import QueueIdUpdateHandler
from db_sender.msh_extractor import MshInfo

SAMPLE_A40_VALID = (
    "MSH|^~\\&|328|LIMS|WRRS|DHCW|20260101120000||ADT^A40^ADT_A39|MSG-A40|P|2.5\r"
    "EVN||20260101120000\r"
    "PID|1||SURVIVOR-777^^^328^PI||SMITH^JOHN||19800101|M\r"
    "MRG|OLD-111^^^328^PI\r"
    "PV1|1|N"
)

SAMPLE_A31_VALID = (
    "MSH|^~\\&|328|LIMS|WRRS|DHCW|20260101120000||ADT^A31^ADT_A05|MSG-A31|P|2.5\r"
    "EVN||20260101120000\r"
    "PID|1||9876543210^^^NHS^NH~LIMS-PAT-01^^^328^PI||SMITH^JOHN||19800101|M\r"
    "PV1|1|N"
)


class TestQueueIdUpdateHandler(unittest.TestCase):

    def setUp(self) -> None:
        self.config = AppConfig(
            connection_string="Endpoint=sb://localhost;",
            service_bus_namespace=None,
            ingress_topic_name="local-inthub-lims-hl7-input",
            ingress_subscription_name="local-inthub-lims-wrrs-sender-sub",
            ingress_session_id="lims-soapserver",
            db_server="localhost",
            db_port=1433,
            db_name="DRS",
            db_stored_procedure="dbo.prQueueIdUpdate",
            db_username="sa",
            db_password="Password123!",  # nosec B106
            db_encrypt="No",
            db_trust_server_certificate="Yes",
            db_connection_timeout=30,
            db_command_timeout=60,
            managed_identity_client_id=None,
            workflow_id="lims-to-wrrs",
            microservice_id="wrrs_idupd_dbsender",
            health_board="WLIMS",
            peer_service="WRRS",
            health_check_hostname=None,
            health_check_port=None,
            log_level="INFO",
            default_is_priority=0,
            max_batch_size=10,
            db_procedure_type="queue_id_update",
            source_system="328",
        )
        self.mock_db_client = MagicMock()
        self.handler = QueueIdUpdateHandler(self.config)

    def test_handle_a40_success(self) -> None:
        msh_info = MshInfo(
            msh_text="MSH|...",
            control_id="MSG-A40",
            message_type="ADT^A40^ADT_A39",
            trigger_event="A40",
            sending_app="328",
        )
        self.handler.handle_message(
            SAMPLE_A40_VALID,
            metadata={},
            msh_info=msh_info,
            db_client=self.mock_db_client,
        )

        self.mock_db_client.execute_queue_id_update.assert_called_once_with(
            provider_patient_identifier=None,
            provider_assigning_authority="328",
            old_identifier="OLD-111",
            old_identifier_assigning_authority="328",
            new_identifier="SURVIVOR-777",
            new_identifier_assigning_authority="328",
        )

    def test_handle_a40_missing_old_identifier_raises_dlq(self) -> None:
        # MRG has empty identifier
        msg = (
            "MSH|^~\\&|328|LIMS|WRRS|DHCW|20260101120000||ADT^A40^ADT_A39|MSG-A40|P|2.5\r"
            "PID|1||SURVIVOR-777^^^328^PI||SMITH^JOHN||19800101|M\r"
            "MRG|\r"
        )
        msh_info = MshInfo(msh_text="MSH|...", control_id="MSG-A40", message_type="ADT^A40", trigger_event="A40")

        with self.assertRaises(DeadLetterMessage) as ctx:
            self.handler.handle_message(msg, {}, msh_info, self.mock_db_client)

        self.assertEqual(ctx.exception.reason, "MissingOldIdentifier")
        self.mock_db_client.execute_queue_id_update.assert_not_called()

    def test_handle_a40_missing_old_assigning_authority_raises_dlq(self) -> None:
        # MRG has old ID but no authority
        msg = (
            "MSH|^~\\&|328|LIMS|WRRS|DHCW|20260101120000||ADT^A40^ADT_A39|MSG-A40|P|2.5\r"
            "PID|1||SURVIVOR-777^^^328^PI||SMITH^JOHN||19800101|M\r"
            "MRG|OLD-111\r"
        )
        msh_info = MshInfo(msh_text="MSH|...", control_id="MSG-A40", message_type="ADT^A40", trigger_event="A40")

        with self.assertRaises(DeadLetterMessage) as ctx:
            self.handler.handle_message(msg, {}, msh_info, self.mock_db_client)

        self.assertEqual(ctx.exception.reason, "MissingOldAssigningAuthority")
        self.mock_db_client.execute_queue_id_update.assert_not_called()

    def test_handle_a40_missing_new_identifier_raises_dlq(self) -> None:
        # PID.3 does not match MRG authority (328 vs 999)
        msg = (
            "MSH|^~\\&|328|LIMS|WRRS|DHCW|20260101120000||ADT^A40^ADT_A39|MSG-A40|P|2.5\r"
            "PID|1||SURVIVOR-777^^^999^PI||SMITH^JOHN||19800101|M\r"
            "MRG|OLD-111^^^328^PI\r"
        )
        msh_info = MshInfo(msh_text="MSH|...", control_id="MSG-A40", message_type="ADT^A40", trigger_event="A40")

        with self.assertRaises(DeadLetterMessage) as ctx:
            self.handler.handle_message(msg, {}, msh_info, self.mock_db_client)

        self.assertEqual(ctx.exception.reason, "MissingNewIdentifier")
        self.mock_db_client.execute_queue_id_update.assert_not_called()

    def test_handle_a31_success(self) -> None:
        msh_info = MshInfo(
            msh_text="MSH|...",
            control_id="MSG-A31",
            message_type="ADT^A31^ADT_A05",
            trigger_event="A31",
            sending_app="328",
        )
        self.handler.handle_message(
            SAMPLE_A31_VALID,
            metadata={},
            msh_info=msh_info,
            db_client=self.mock_db_client,
        )

        self.mock_db_client.execute_queue_id_update.assert_called_once_with(
            provider_patient_identifier="LIMS-PAT-01",
            provider_assigning_authority="328",
            old_identifier=None,
            old_identifier_assigning_authority=None,
            new_identifier="9876543210",
            new_identifier_assigning_authority="NHS",
        )

    def test_handle_a31_dynamic_source_system_from_metadata(self) -> None:
        msg = (
            "MSH|^~\\&|SYS_B|HOSP|WRRS|DHCW|20260101120000||ADT^A31^ADT_A05|MSG-A31|P|2.5\r"
            "PID|1||9876543210^^^NHS^NH~CUSTOM-PAT^^^SYS_B^PI||SMITH^JOHN||19800101|M\r"
        )
        msh_info = MshInfo(
            msh_text="MSH|...",
            control_id="MSG-A31",
            message_type="ADT^A31",
            trigger_event="A31",
            sending_app="SYS_B",
        )
        self.handler.handle_message(
            msg,
            metadata={"source_system": "SYS_B"},
            msh_info=msh_info,
            db_client=self.mock_db_client,
        )

        self.mock_db_client.execute_queue_id_update.assert_called_once_with(
            provider_patient_identifier="CUSTOM-PAT",
            provider_assigning_authority="SYS_B",
            old_identifier=None,
            old_identifier_assigning_authority=None,
            new_identifier="9876543210",
            new_identifier_assigning_authority="NHS",
        )

    def test_handle_a31_missing_provider_identifier_raises_dlq(self) -> None:
        # Has NHS ID but missing 328 ID
        msg = (
            "MSH|^~\\&|328|LIMS|WRRS|DHCW|20260101120000||ADT^A31^ADT_A05|MSG-A31|P|2.5\r"
            "PID|1||9876543210^^^NHS^NH||SMITH^JOHN||19800101|M\r"
        )
        msh_info = MshInfo(msh_text="MSH|...", control_id="MSG-A31", message_type="ADT^A31", trigger_event="A31")

        with self.assertRaises(DeadLetterMessage) as ctx:
            self.handler.handle_message(msg, {}, msh_info, self.mock_db_client)

        self.assertEqual(ctx.exception.reason, "MissingLimsIdentifier")
        self.mock_db_client.execute_queue_id_update.assert_not_called()

    def test_handle_a31_missing_nhs_identifier_raises_dlq(self) -> None:
        # Has 328 ID but missing NHS ID
        msg = (
            "MSH|^~\\&|328|LIMS|WRRS|DHCW|20260101120000||ADT^A31^ADT_A05|MSG-A31|P|2.5\r"
            "PID|1||LIMS-PAT-01^^^328^PI||SMITH^JOHN||19800101|M\r"
        )
        msh_info = MshInfo(msh_text="MSH|...", control_id="MSG-A31", message_type="ADT^A31", trigger_event="A31")

        with self.assertRaises(DeadLetterMessage) as ctx:
            self.handler.handle_message(msg, {}, msh_info, self.mock_db_client)

        self.assertEqual(ctx.exception.reason, "MissingNhsIdentifier")
        self.mock_db_client.execute_queue_id_update.assert_not_called()

    def test_handle_unsupported_trigger_raises_dlq(self) -> None:
        msg = (
            "MSH|^~\\&|328|LIMS|WRRS|DHCW|20260101120000||ADT^A04^ADT_A01|MSG-A04|P|2.5\r"
            "PID|1||12345^^^328^PI||SMITH^JOHN||19800101|M\r"
        )
        msh_info = MshInfo(msh_text="MSH|...", control_id="MSG-A04", message_type="ADT^A04", trigger_event="A04")

        with self.assertRaises(DeadLetterMessage) as ctx:
            self.handler.handle_message(msg, {}, msh_info, self.mock_db_client)

        self.assertEqual(ctx.exception.reason, "UnsupportedTriggerEvent")
        self.mock_db_client.execute_queue_id_update.assert_not_called()


if __name__ == "__main__":
    unittest.main()
