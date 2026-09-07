import unittest
from unittest.mock import MagicMock, patch

from message_store_service.application import main


class TestApplication(unittest.TestCase):
    @patch("message_store_service.application.MessageStoreService")
    @patch("message_store_service.application.MAX_BATCH_SIZE", 100)
    def test_main_creates_and_runs_service(self, mock_service_class: MagicMock) -> None:
        # Arrange
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        # Act
        main()

        # Assert
        mock_service_class.assert_called_once_with(100)
        mock_service.run.assert_called_once()


if __name__ == "__main__":
    unittest.main()

