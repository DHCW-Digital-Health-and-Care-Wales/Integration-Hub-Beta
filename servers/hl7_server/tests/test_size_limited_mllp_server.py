import unittest
from typing import Any, Dict, Tuple
from unittest.mock import Mock

from event_logger_lib.event_logger import EventLogger

from hl7_server.generic_handler import GenericHandler
from hl7_server.hl7_validator import HL7Validator
from hl7_server.size_limited_mllp_server import SizeLimitedMLLPServer


class TestSizeLimitedMLLPServer(unittest.TestCase):

    def setUp(self) -> None:
        self.mock_sender_client = Mock()
        self.mock_event_logger = Mock(spec=EventLogger)
        self.mock_validator = Mock(spec=HL7Validator)
        self.test_host = "127.0.0.1"
        self.test_port = 9999

        self.test_handlers: Dict[str, Tuple[Any, ...]] = {
            "ADT^A31^ADT_A05": (
                GenericHandler,
                self.mock_sender_client,
                self.mock_event_logger,
                self.mock_validator,
                "test_flow"
            ),
        }

    def test_server_initializes_with_provided_message_size_limit(self) -> None:
        test_size_limit = 512000  # 500KB for testing

        server = SizeLimitedMLLPServer(
            self.test_host,
            self.test_port,
            self.test_handlers,
            max_message_size_bytes=test_size_limit,
            event_logger=self.mock_event_logger
        )

        self.assertEqual(server.max_message_size_bytes, test_size_limit)
        self.assertEqual(server.event_logger, self.mock_event_logger)


if __name__ == '__main__':
    unittest.main()
