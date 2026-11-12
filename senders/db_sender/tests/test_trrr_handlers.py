import unittest
from unittest.mock import MagicMock

from message_bus_lib.dead_letter import DeadLetterMessage

from db_sender.app_config import AppConfig
from db_sender.handlers import TrrrIdUpdateHandler, TrrrMergeHandler, create_handler
from db_sender.msh_extractor import MshInfo

A31_WITH_NHS = (
    "MSH|^~\\&|328|LIMS|TRRR|DHCW|20260101120000||ADT^A31^ADT_A05|MSG-A31|P|2.5\r"
    "PID|1||9876543210^^^NHS^NH~0012345^^^328^PI||SMITH^JOHN||19800101|M\r"
)

A40_WITH_NHS = (
    "MSH|^~\\&|154|LIMS|TRRR|DHCW|20260101120000||ADT^A40^ADT_A39|MSG-A40|P|2.5\r"
    "PID|1||9876543210^^^NHS^NH~SURV-1^^^154^PI||SMITH^JOHN||19800101|M\r"
    "MRG|OLD-1^^^154^PI\r"
)

A40_MERGE_ONLY = (
    "MSH|^~\\&|154|LIMS|TRRR|DHCW|20260101120000||ADT^A40^ADT_A39|MSG-A40|P|2.5\r"
    "PID|1||SURV-1^^^154^PI||SMITH^JOHN||19800101|M\r"
    "MRG|OLD-1^^^154^PI\r"
)

A05_MESSAGE = (
    "MSH|^~\\&|328|LIMS|TRRR|DHCW|20260101120000||ADT^A05^ADT_A05|MSG-A05|P|2.5\r"
    "PID|1||9876543210^^^NHS^NH~0012345^^^328^PI||SMITH^JOHN||19800101|M\r"
)


def _config(procedure_type: str, stored_procedure: str) -> AppConfig:
    return AppConfig(
        connection_string="Endpoint=sb://localhost;",
        service_bus_namespace=None,
        ingress_topic_name="local-inthub-lims-hl7-input",
        ingress_subscription_name="local-inthub-lims-trrr-sender-sub",
        ingress_session_id="lims-soapserver",
        db_server="localhost",
        db_port=1433,
        db_name="Clinical_Results",
        db_stored_procedure=stored_procedure,
        db_username="sa",
        db_password="Password123!",  # nosec B106
        db_encrypt="No",
        db_trust_server_certificate="Yes",
        db_connection_timeout=30,
        db_command_timeout=60,
        managed_identity_client_id=None,
        workflow_id="lims-to-trrr",
        microservice_id="trrr_idupd_dbsender",
        health_board="SHARED",
        peer_service="TRRR",
        health_check_hostname=None,
        health_check_port=None,
        log_level="INFO",
        default_is_priority=0,
        max_batch_size=10,
        db_procedure_type=procedure_type,
        source_system="328",
    )


def _msh(trigger: str, sending_app: str) -> MshInfo:
    return MshInfo(
        msh_text="MSH|...",
        control_id="MSG-1",
        message_type=f"ADT^{trigger}",
        trigger_event=trigger,
        sending_app=sending_app,
    )


class TestTrrrIdUpdateHandler(unittest.TestCase):
    def setUp(self) -> None:
        self.handler = TrrrIdUpdateHandler(_config("trrr_id_update", "dbo.TRRRIDUpdate"))
        self.db_client = MagicMock()

    def test_a31_success_preserves_leading_zeroes(self) -> None:
        self.handler.handle_message(A31_WITH_NHS, {"SourceSystem": "328"}, _msh("A31", "328"), self.db_client)

        self.db_client.execute_trrr_id_update.assert_called_once_with(
            lims_identifier="0012345",
            new_identifier="9876543210",
            new_identifier_assigning_authority="NHS",
        )

    def test_a40_uses_sending_application_as_lims_authority(self) -> None:
        self.handler.handle_message(A40_WITH_NHS, {}, _msh("A40", "154"), self.db_client)

        self.db_client.execute_trrr_id_update.assert_called_once_with(
            lims_identifier="SURV-1",
            new_identifier="9876543210",
            new_identifier_assigning_authority="NHS",
        )

    def test_a40_without_nhs_identifier_is_dead_lettered(self) -> None:
        with self.assertRaises(DeadLetterMessage) as ctx:
            self.handler.handle_message(A40_MERGE_ONLY, {}, _msh("A40", "154"), self.db_client)

        self.assertEqual(ctx.exception.reason, "MissingNhsIdentifier")
        self.db_client.execute_trrr_id_update.assert_not_called()

    def test_a40_without_sending_application_is_dead_lettered(self) -> None:
        with self.assertRaises(DeadLetterMessage) as ctx:
            self.handler.handle_message(A40_WITH_NHS, {}, _msh("A40", ""), self.db_client)

        self.assertEqual(ctx.exception.reason, "MissingSendingLimsAuthority")

    def test_missing_lims_identifier_is_dead_lettered(self) -> None:
        with self.assertRaises(DeadLetterMessage) as ctx:
            self.handler.handle_message(A31_WITH_NHS, {"SourceSystem": "999"}, _msh("A31", "999"), self.db_client)

        self.assertEqual(ctx.exception.reason, "MissingLimsIdentifier")

    def test_a05_is_not_accepted(self) -> None:
        with self.assertRaises(DeadLetterMessage) as ctx:
            self.handler.handle_message(A05_MESSAGE, {}, _msh("A05", "328"), self.db_client)

        self.assertEqual(ctx.exception.reason, "UnsupportedTriggerEvent")
        self.db_client.execute_trrr_id_update.assert_not_called()


class TestTrrrMergeHandler(unittest.TestCase):
    def setUp(self) -> None:
        self.handler = TrrrMergeHandler(_config("trrr_merge", "dbo.TRRRIDMerge"))
        self.db_client = MagicMock()

    def test_a40_merge_success(self) -> None:
        self.handler.handle_message(A40_MERGE_ONLY, {}, _msh("A40", "154"), self.db_client)

        self.db_client.execute_trrr_merge.assert_called_once_with(
            old_identifier="OLD-1",
            old_identifier_assigning_authority="154",
            new_identifier="SURV-1",
            new_identifier_assigning_authority="154",
        )

    def test_a40_with_nhs_identifier_also_merges(self) -> None:
        self.handler.handle_message(A40_WITH_NHS, {}, _msh("A40", "154"), self.db_client)

        self.db_client.execute_trrr_merge.assert_called_once()

    def test_non_a40_is_dead_lettered(self) -> None:
        with self.assertRaises(DeadLetterMessage) as ctx:
            self.handler.handle_message(A31_WITH_NHS, {}, _msh("A31", "328"), self.db_client)

        self.assertEqual(ctx.exception.reason, "UnsupportedTriggerEvent")
        self.db_client.execute_trrr_merge.assert_not_called()

    def test_missing_mrg_is_dead_lettered(self) -> None:
        message = A40_MERGE_ONLY.split("MRG")[0]
        with self.assertRaises(DeadLetterMessage) as ctx:
            self.handler.handle_message(message, {}, _msh("A40", "154"), self.db_client)

        self.assertEqual(ctx.exception.reason, "MissingOldIdentifier")

    def test_missing_surviving_identifier_is_dead_lettered(self) -> None:
        message = A40_MERGE_ONLY.replace("SURV-1^^^154^PI", "SURV-1^^^999^PI")
        with self.assertRaises(DeadLetterMessage) as ctx:
            self.handler.handle_message(message, {}, _msh("A40", "154"), self.db_client)

        self.assertEqual(ctx.exception.reason, "MissingNewIdentifier")


class TestTrrrHandlerFactory(unittest.TestCase):
    def test_factory_selects_trrr_handlers(self) -> None:
        self.assertIsInstance(create_handler(_config("trrr_id_update", "dbo.TRRRIDUpdate")), TrrrIdUpdateHandler)
        self.assertIsInstance(create_handler(_config("trrr_merge", "dbo.TRRRIDMerge")), TrrrMergeHandler)


if __name__ == "__main__":
    unittest.main()
