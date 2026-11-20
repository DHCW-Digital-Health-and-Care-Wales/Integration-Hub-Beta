import unittest
from unittest.mock import MagicMock

from message_bus_lib.dead_letter import DeadLetterMessage

from db_sender.app_config import AppConfig
from db_sender.handlers import UpdateIdentifierHandler, create_handler
from db_sender.msh_extractor import MshInfo

# CAV PMS (MSH.3 = 140) A40 merge as HL7v2 XML: old ID in MRG-1, new ID is the PID-3 entry with authority 140.
SAMPLE_A40_XML = """<ADT_A39>
<MSH><MSH.1>|</MSH.1><MSH.2>^~\\&amp;</MSH.2><MSH.3><HD.1>140</HD.1></MSH.3>
<MSH.9><MSG.1>ADT</MSG.1><MSG.2>A40</MSG.2><MSG.3>ADT_A39</MSG.3></MSH.9>
<MSH.10>bcc3a4d658d74c03a8915356769cc7f6</MSH.10></MSH>
<ADT_A39.PATIENT>
<PID>
<PID.3><CX.1>7025040525</CX.1><CX.4><HD.1>NHS</HD.1></CX.4><CX.5>NH</CX.5></PID.3>
<PID.3><CX.1>{new_id}</CX.1><CX.4><HD.1>140</HD.1></CX.4><CX.5>PI</CX.5></PID.3>
</PID>
<MRG><MRG.1><CX.1>{old_id}</CX.1><CX.4><HD.1>{old_auth}</HD.1></CX.4></MRG.1></MRG>
</ADT_A39.PATIENT>
</ADT_A39>"""


def _a40_xml(old_id: str = "U692047", old_auth: str = "140", new_id: str = "U363137") -> str:
    return SAMPLE_A40_XML.format(old_id=old_id, old_auth=old_auth, new_id=new_id)


def _msh(trigger: str = "A40") -> MshInfo:
    return MshInfo(
        msh_text="MSH|...",
        control_id="MSG-1",
        message_type=f"ADT^{trigger}",
        trigger_event=trigger,
        sending_app="140",
    )


def _config(procedure_type: str = "update_identifier") -> AppConfig:
    return AppConfig(
        connection_string="Endpoint=sb://localhost;",
        service_bus_namespace=None,
        ingress_topic_name="local-inthub-pms-sender-ingress",
        ingress_subscription_name="local-inthub-pms-wcrs-sender-sub",
        ingress_session_id="pms-to-mpi",
        db_server="localhost",
        db_port=1433,
        db_name="NDR",
        db_stored_procedure="dbo.spUpdateIdentifier",
        db_username="sa",
        db_password="Password123!",  # nosec B106
        db_encrypt="No",
        db_trust_server_certificate="Yes",
        db_connection_timeout=30,
        db_command_timeout=60,
        managed_identity_client_id=None,
        workflow_id="cav-pms-to-wcrs",
        microservice_id="wcrs_updident_dbsender",
        health_board="PMS",
        peer_service="WCRS",
        health_check_hostname=None,
        health_check_port=None,
        log_level="INFO",
        default_is_priority=0,
        max_batch_size=10,
        db_procedure_type=procedure_type,
    )


class TestUpdateIdentifierHandler(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_db_client = MagicMock()
        self.handler = UpdateIdentifierHandler(_config())

    def test_factory_creates_handler_for_update_identifier(self) -> None:
        self.assertIsInstance(create_handler(_config("update_identifier")), UpdateIdentifierHandler)

    def test_a40_xml_maps_old_and_new_identifiers(self) -> None:
        self.handler.handle_message(_a40_xml(), {}, _msh(), self.mock_db_client)

        self.mock_db_client.execute_update_identifier.assert_called_once_with(
            old_identifier="U692047",
            old_identifier_assigning_authority="140",
            new_identifier="U363137",
        )

    def test_a40_er7_maps_old_and_new_identifiers(self) -> None:
        msg = (
            "MSH|^~\\&|140|140|200|200|202610261222||ADT^A40^ADT_A39|MSG-1|P|2.5\r"
            "PID|1||7025040525^^^NHS^NH~U363137^^^140^PI||TEST^TEST\r"
            "MRG|U692047^^^140\r"
        )
        self.handler.handle_message(msg, {}, _msh(), self.mock_db_client)

        self.mock_db_client.execute_update_identifier.assert_called_once_with(
            old_identifier="U692047",
            old_identifier_assigning_authority="140",
            new_identifier="U363137",
        )

    def test_only_pid3_entry_with_matching_authority_is_selected(self) -> None:
        # The NHS number identifier in PID-3 must not be picked for authority 140.
        self.handler.handle_message(_a40_xml(), {}, _msh(), self.mock_db_client)

        kwargs = self.mock_db_client.execute_update_identifier.call_args.kwargs
        self.assertNotEqual(kwargs["new_identifier"], "7025040525")

    def test_leading_zeroes_are_preserved_as_text(self) -> None:
        msg = _a40_xml(old_id="000123", new_id="000456")
        self.handler.handle_message(msg, {}, _msh(), self.mock_db_client)

        kwargs = self.mock_db_client.execute_update_identifier.call_args.kwargs
        self.assertEqual(kwargs["old_identifier"], "000123")
        self.assertEqual(kwargs["new_identifier"], "000456")

    def test_multiple_patient_groups_xml_raises_dlq_before_db_write(self) -> None:
        # Two PID/MRG groups: only the first MRG would be read, so the whole message must be rejected.
        group = "<ADT_A39.PATIENT>" + _a40_xml().split("<ADT_A39.PATIENT>")[1].split("</ADT_A39.PATIENT>")[0]
        msg = _a40_xml().replace("</ADT_A39>", group + "</ADT_A39.PATIENT></ADT_A39>")

        with self.assertRaises(DeadLetterMessage) as ctx:
            self.handler.handle_message(msg, {}, _msh(), self.mock_db_client)

        self.assertEqual(ctx.exception.reason, "MultiplePatientGroups")
        self.mock_db_client.execute_update_identifier.assert_not_called()

    def test_multiple_patient_groups_er7_raises_dlq_before_db_write(self) -> None:
        msg = (
            "MSH|^~\\&|140|140|200|200|202610261222||ADT^A40^ADT_A39|MSG-1|P|2.5\r"
            "PID|1||U363137^^^140^PI\rMRG|U692047^^^140\r"
            "PID|1||U999999^^^140^PI\rMRG|U888888^^^140\r"
        )

        with self.assertRaises(DeadLetterMessage) as ctx:
            self.handler.handle_message(msg, {}, _msh(), self.mock_db_client)

        self.assertEqual(ctx.exception.reason, "MultiplePatientGroups")
        self.mock_db_client.execute_update_identifier.assert_not_called()

    def test_missing_old_identifier_raises_dlq(self) -> None:
        with self.assertRaises(DeadLetterMessage) as ctx:
            self.handler.handle_message(_a40_xml(old_id=""), {}, _msh(), self.mock_db_client)

        self.assertEqual(ctx.exception.reason, "MissingOldIdentifier")
        self.mock_db_client.execute_update_identifier.assert_not_called()

    def test_missing_old_assigning_authority_raises_dlq(self) -> None:
        with self.assertRaises(DeadLetterMessage) as ctx:
            self.handler.handle_message(_a40_xml(old_auth=""), {}, _msh(), self.mock_db_client)

        self.assertEqual(ctx.exception.reason, "MissingOldAssigningAuthority")
        self.mock_db_client.execute_update_identifier.assert_not_called()

    def test_missing_new_identifier_raises_dlq(self) -> None:
        # MRG authority 999 matches no PID-3 entry
        with self.assertRaises(DeadLetterMessage) as ctx:
            self.handler.handle_message(_a40_xml(old_auth="999"), {}, _msh(), self.mock_db_client)

        self.assertEqual(ctx.exception.reason, "MissingNewIdentifier")
        self.mock_db_client.execute_update_identifier.assert_not_called()

    def test_non_a40_trigger_raises_dlq(self) -> None:
        with self.assertRaises(DeadLetterMessage) as ctx:
            self.handler.handle_message(_a40_xml(), {}, _msh("A31"), self.mock_db_client)

        self.assertEqual(ctx.exception.reason, "UnsupportedTriggerEvent")
        self.mock_db_client.execute_update_identifier.assert_not_called()

    def test_unknown_trigger_falls_back_to_message_body(self) -> None:
        msh_info = MshInfo(msh_text="MSH|...", control_id="MSG-1", message_type="", trigger_event="UNKNOWN")
        self.handler.handle_message(_a40_xml(), {}, msh_info, self.mock_db_client)

        self.mock_db_client.execute_update_identifier.assert_called_once()


if __name__ == "__main__":
    unittest.main()
