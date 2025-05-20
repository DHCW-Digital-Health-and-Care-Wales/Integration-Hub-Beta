import unittest
from unittest.mock import MagicMock

from dhcw_nhs_wales_inthub.wpas_validator.WpasMessageValidator import WpasMessageValidator


class TestWpasMessageValidator(unittest.TestCase):
    def setUp(self) -> None:
        self.config = MagicMock()
        self.receiver = MagicMock()
        self.xml_validator = MagicMock()
        self.sender = MagicMock()
        self.validator = WpasMessageValidator(
            config=self.config, receiver=self.receiver, validator=self.xml_validator, sender=self.sender
        )
        super().setUp()

    def test_process_message(self) -> None:
        message = MagicMock()

        self.validator.process_message(message=message)

        self.xml_validator.validate.assert_called_once()
        self.sender.send_message.assert_called_once()
