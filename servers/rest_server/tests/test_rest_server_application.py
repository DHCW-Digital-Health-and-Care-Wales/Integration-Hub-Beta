import unittest
from typing import cast

from rest_server.app_config import AppConfig
from rest_server.content_adapters.soap_adapter import SoapContentAdapter
from rest_server.content_adapters.xml_raw_adapter import XmlRawContentAdapter
from rest_server.rest_server_application import build_content_adapter, build_validator
from rest_server.validators.hl7_xsd_validator import Hl7XsdValidator
from rest_server.validators.no_op_validator import NoOpValidator
from rest_server.validators.xsd_validator import XsdValidator


def _config(**overrides: object) -> AppConfig:
    defaults: dict[str, object] = dict(
        connection_string="Endpoint=sb://localhost",
        egress_queue_name="egress-queue",
        egress_topic_name=None,
        egress_session_id="rest-session",
        service_bus_namespace=None,
        message_store_queue_name="message-store",
        workflow_id="workflow-rest",
        microservice_id="rest-server",
        health_board="test-board",
        peer_service="hl7-sender",
        health_check_hostname=None,
        health_check_port=None,
        host="127.0.0.1",
        port=8080,
        endpoint_path="/ingest",
        content_adapter="xml-raw",
        validator_type="none",
        validation_schema=None,
        allowed_hl7_structures=["ADT_A05"],
        allowed_source_identifiers=[],
        source_identifier_locator=None,
        message_control_id_locator=None,
        output_format="raw",
        pipeline="generic",
        environment="DEV",
        hl7_version=None,
        sending_app=None,
        hl7_validation_flow=None,
        hl7_validation_standard=None,
        wrrs_queue_name=None,
        wrrs_topic_name=None,
        wrrs_egress_session_id=None,
        wrrs_workflow_id=None,
    )
    defaults.update(overrides)
    return AppConfig(**defaults)  # type: ignore[arg-type]


class TestBuildContentAdapter(unittest.TestCase):
    def test_soap_adapter(self) -> None:
        adapter = build_content_adapter(_config(content_adapter="soap"))
        self.assertIsInstance(adapter, SoapContentAdapter)

    def test_xml_raw_adapter(self) -> None:
        adapter = build_content_adapter(
            _config(
                content_adapter="xml-raw",
                source_identifier_locator=["Header", "SourceSystem"],
            )
        )
        self.assertIsInstance(adapter, XmlRawContentAdapter)
        self.assertEqual(cast(XmlRawContentAdapter, adapter).source_identifier_path, ["Header", "SourceSystem"])

    def test_unsupported_adapter_raises(self) -> None:
        config = _config(content_adapter="xml-raw")
        object.__setattr__(config, "content_adapter", "carrier-pigeon")
        with self.assertRaises(RuntimeError):
            build_content_adapter(config)


class TestBuildValidator(unittest.TestCase):
    def test_hl7_xsd_validator(self) -> None:
        validator = build_validator(_config(validator_type="hl7-xsd", validation_schema="phw"))
        self.assertIsInstance(validator, Hl7XsdValidator)
        self.assertEqual(cast(Hl7XsdValidator, validator).schema_group, "phw")

    def test_xsd_validator(self) -> None:
        validator = build_validator(_config(validator_type="xsd", validation_schema="/schemas/partner.xsd"))
        self.assertIsInstance(validator, XsdValidator)
        self.assertEqual(cast(XsdValidator, validator).schema_path, "/schemas/partner.xsd")

    def test_none_validator(self) -> None:
        validator = build_validator(_config(validator_type="none"))
        self.assertIsInstance(validator, NoOpValidator)

    def test_unsupported_validator_raises(self) -> None:
        config = _config(validator_type="none")
        object.__setattr__(config, "validator_type", "vibes")
        with self.assertRaises(RuntimeError):
            build_validator(config)


if __name__ == "__main__":
    unittest.main()
