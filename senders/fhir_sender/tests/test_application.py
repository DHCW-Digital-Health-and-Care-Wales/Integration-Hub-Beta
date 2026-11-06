import unittest
from unittest.mock import MagicMock, patch

from message_bus_lib.dead_letter import DeadLetterMessage

from fhir_sender import application
from fhir_sender.errors import (
    AuthorizationDeliveryError,
    PermanentDeliveryError,
    TransientDeliveryError,
)

VALID_BUNDLE = '{"resourceType":"Bundle","type":"message","entry":[]}'


def _message(body: str) -> MagicMock:
    message = MagicMock()
    message.body = [body.encode("utf-8")]
    return message


class ProcessMessageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = MagicMock()
        self.event_logger = MagicMock()
        self.metric_sender = MagicMock()
        patcher = patch.object(application, "extract_metadata", return_value={"CorrelationId": "corr-1"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _process(self, body: str = VALID_BUNDLE) -> bool:
        return application._process_message(_message(body), self.client, self.event_logger, self.metric_sender)

    def test_delivered_message_is_completed_and_counted(self) -> None:
        self.assertTrue(self._process())
        self.client.send_bundle.assert_called_once_with(VALID_BUNDLE)
        self.metric_sender.send_message_sent_metric.assert_called_once()
        self.event_logger.log_message_processed.assert_called_once()

    def test_invalid_bundle_is_dead_lettered_without_sending(self) -> None:
        for body in ("not json", '{"resourceType":"Patient"}', '{"resourceType":"Bundle","type":"transaction"}', "[]"):
            with self.subTest(body=body), self.assertRaises(DeadLetterMessage):
                self._process(body)
        self.client.send_bundle.assert_not_called()

    def test_permanent_rejection_is_dead_lettered_and_logged(self) -> None:
        self.client.send_bundle.side_effect = PermanentDeliveryError(400, "invalid/x: bad")
        with self.assertRaises(DeadLetterMessage) as ctx:
            self._process()
        self.assertIn("400", ctx.exception.description)
        self.event_logger.log_message_failed.assert_called_once()
        self.metric_sender.send_message_sent_metric.assert_not_called()

    def test_authorization_failure_alerts_and_abandons(self) -> None:
        self.client.send_bundle.side_effect = AuthorizationDeliveryError(403, "forbidden")
        with self.assertLogs(application.logger, level="ERROR") as logs:
            self.assertFalse(self._process())
        self.assertTrue(any("ALERT" in line for line in logs.output))

    def test_transient_failure_abandons(self) -> None:
        self.client.send_bundle.side_effect = TransientDeliveryError("gave up")
        self.assertFalse(self._process())
        self.event_logger.log_message_failed.assert_called_once()


if __name__ == "__main__":
    unittest.main()
