import unittest
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

from metric_sender_lib.metric_sender import MetricSender


class TestMetricSender(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow_id = "phw-mpi"
        self.microservice_id = "test_microservice"
        self.health_board = "PHW"
        self.peer_service = "MPI"
        self.test_connection_string = "InstrumentationKey=test-key;IngestionEndpoint=https://test.com/"

        self.env_patcher = patch.dict('os.environ', {}, clear=True)
        self.env_patcher.start()

    def tearDown(self) -> None:
        self.env_patcher.stop()

    def _create_metric_sender_with_azure_monitor(self, health_board: Optional[str] = None, peer_service: Optional[str] = None) -> MetricSender:
        with patch.object(MetricSender, '_initialize_azure_monitor'):
            return MetricSender(self.workflow_id, self.microservice_id, health_board or self.health_board, peer_service or self.peer_service)

    def _get_expected_attributes(self, custom_attrs: Optional[Dict[str, Any]] = None, health_board: Optional[str] = None, peer_service: Optional[str] = None) -> Dict[str, Any]:
        expected: Dict[str, Any] = {
            "workflow_id": self.workflow_id,
            "microservice_id": self.microservice_id,
            "health_board": health_board or self.health_board,
            "peer_service": peer_service or self.peer_service,
        }
        if custom_attrs:
            expected.update(custom_attrs)
        return expected

    @patch('metric_sender_lib.metric_sender.logger')
    def test_init_scenarios_where_azure_monitor_disabled(self, mock_logger: MagicMock) -> None:
        test_cases = [
            {
                'name': 'without_connection_string',
                'env': {}
            },
            {
                'name': 'with_empty_connection_string',
                'env': {'APPLICATIONINSIGHTS_CONNECTION_STRING': '   '}
            }
        ]

        for test_case in test_cases:
            with self.subTest(test_case['name']):
                # Arrange
                log_message = ("Azure Monitor metrics is disabled - APPLICATIONINSIGHTS_CONNECTION_STRING not set or empty. "
                              "Metrics will be logged to standard logger.")
                with patch.dict('os.environ', test_case['env'], clear=True):
                    mock_logger.reset_mock()

                    # Act
                    metric_sender = MetricSender(self.workflow_id, self.microservice_id, self.health_board, self.peer_service)

                    # Assert
                    self.assertEqual(metric_sender.workflow_id, self.workflow_id)
                    self.assertEqual(metric_sender.microservice_id, self.microservice_id)
                    self.assertEqual(metric_sender.health_board, self.health_board)
                    self.assertEqual(metric_sender.peer_service, self.peer_service)
                    self.assertEqual(metric_sender.azure_monitor_enabled, False)
                    self.assertEqual(metric_sender._counters, {})
                    mock_logger.info.assert_called_once_with(log_message)

    @patch('metric_sender_lib.metric_sender.logger')
    @patch('metric_sender_lib.metric_sender.configure_azure_monitor')
    @patch('metric_sender_lib.metric_sender.metrics.get_meter')
    @patch.dict('os.environ', {'APPLICATIONINSIGHTS_CONNECTION_STRING': 'test-connection-string'})
    def test_init_with_connection_string_success(self, mock_get_meter: MagicMock,
                                                mock_configure: MagicMock, mock_logger: MagicMock) -> None:
        # Arrange
        mock_meter = MagicMock()
        mock_get_meter.return_value = mock_meter

        with patch.object(MetricSender, '_get_credential') as mock_get_credential:
            mock_credential = MagicMock()
            mock_get_credential.return_value = mock_credential

            # Act
            metric_sender = MetricSender(self.workflow_id, self.microservice_id, self.health_board, self.peer_service)

            # Assert
            self.assertTrue(metric_sender.azure_monitor_enabled)
            self.assertEqual(metric_sender._meter, mock_meter)
            mock_get_credential.assert_called_once()
            mock_configure.assert_called_once_with(credential=mock_credential)
            mock_get_meter.assert_called_once_with('metric_sender_lib.metric_sender')
            mock_logger.info.assert_called_with("Azure Monitor metrics initialized successfully")

    @patch('metric_sender_lib.metric_sender.logger')
    @patch('metric_sender_lib.metric_sender.configure_azure_monitor')
    @patch.dict('os.environ', {'APPLICATIONINSIGHTS_CONNECTION_STRING': 'test-connection-string'})
    def test_init_with_azure_monitor_failure(self, mock_configure: MagicMock, mock_logger: MagicMock) -> None:
        # Arrange
        mock_configure.side_effect = Exception("Azure Monitor setup failed")

        with patch.object(MetricSender, '_get_credential') as mock_get_credential:
            mock_get_credential.return_value = MagicMock()

            # Act & Assert
            with self.assertRaises(Exception) as context:
                MetricSender(self.workflow_id, self.microservice_id, self.health_board, self.peer_service)

            self.assertEqual(str(context.exception), "Azure Monitor setup failed")
            mock_logger.error.assert_called_with("Failed to initialize Azure Monitor metrics: Azure Monitor setup failed")

    @patch('metric_sender_lib.metric_sender.logger')
    @patch('metric_sender_lib.metric_sender.ManagedIdentityCredential')
    @patch.dict('os.environ', {'INSIGHTS_UAMI_CLIENT_ID': 'test-client-id'})
    def test_get_credential_with_uami_client_id(self, mock_managed_identity: MagicMock,
                                                mock_logger: MagicMock) -> None:
        # Arrange
        mock_credential = MagicMock()
        mock_managed_identity.return_value = mock_credential
        metric_sender = MetricSender(self.workflow_id, self.microservice_id, self.health_board, self.peer_service)

        # Act
        credential = metric_sender._get_credential()

        # Assert
        self.assertEqual(credential, mock_credential)
        mock_managed_identity.assert_called_once_with(client_id='test-client-id')
        mock_logger.info.assert_called_with("Using ManagedIdentityCredential with client_id: test-client-id")

    @patch('metric_sender_lib.metric_sender.logger')
    @patch('metric_sender_lib.metric_sender.DefaultAzureCredential')
    def test_get_credential_without_uami_client_id_scenarios(self, mock_default_credential: MagicMock,
                                                             mock_logger: MagicMock) -> None:
        test_cases = [
            {
                'name': 'with_empty_uami_client_id',
                'env': {'INSIGHTS_UAMI_CLIENT_ID': '   '}
            },
            {
                'name': 'without_uami_client_id',
                'env': {}
            }
        ]

        for test_case in test_cases:
            with self.subTest(test_case['name']):
                # Arrange
                with patch.dict('os.environ', test_case['env'], clear=True):
                    mock_credential = MagicMock()
                    mock_default_credential.reset_mock()
                    mock_default_credential.return_value = mock_credential
                    mock_logger.reset_mock()

                    metric_sender = MetricSender(self.workflow_id, self.microservice_id, self.health_board, self.peer_service)

                    # Act
                    credential = metric_sender._get_credential()

                    # Assert
                    self.assertEqual(credential, mock_credential)
                    mock_default_credential.assert_called_once()
                    mock_logger.info.assert_called_with("Using DefaultAzureCredential (INSIGHTS_UAMI_CLIENT_ID not set)")

    @patch('metric_sender_lib.metric_sender.logger')
    @patch.dict('os.environ', {'APPLICATIONINSIGHTS_CONNECTION_STRING': 'test-connection-string'})
    def test_get_or_create_counter_new_counter(self, mock_logger: MagicMock) -> None:
        # Arrange
        metric_sender = self._create_metric_sender_with_azure_monitor()
        mock_meter = MagicMock()
        mock_counter = MagicMock()
        mock_meter.create_counter.return_value = mock_counter
        metric_sender._meter = mock_meter

        # Act
        result = metric_sender._get_or_create_counter("test_metric")

        # Assert
        self.assertEqual(result, mock_counter)
        self.assertEqual(metric_sender._counters["test_metric"], mock_counter)
        mock_meter.create_counter.assert_called_once_with(
            name="test_metric",
            description="Counter for test_metric"
        )
        mock_logger.debug.assert_called_with("Created new counter for metric: test_metric")

    @patch('metric_sender_lib.metric_sender.logger')
    @patch.dict('os.environ', {'APPLICATIONINSIGHTS_CONNECTION_STRING': 'test-connection-string'})
    def test_get_or_create_counter_existing_counter(self, mock_logger: MagicMock) -> None:
        # Arrange
        metric_sender = self._create_metric_sender_with_azure_monitor()
        mock_counter = MagicMock()
        metric_sender._counters["test_metric"] = mock_counter

        # Act
        result = metric_sender._get_or_create_counter("test_metric")

        # Assert
        self.assertEqual(result, mock_counter)
        self.assertEqual(len(metric_sender._counters), 1)  # Ensure no new counter was created

    @patch('metric_sender_lib.metric_sender.logger')
    @patch.dict('os.environ', {'APPLICATIONINSIGHTS_CONNECTION_STRING': 'test-connection-string'})
    def test_send_metric_with_azure_monitor_enabled(self, mock_logger: MagicMock) -> None:
        # Arrange
        metric_sender = self._create_metric_sender_with_azure_monitor()
        metric_sender.azure_monitor_enabled = True
        metric_sender._meter = MagicMock()
        mock_counter = MagicMock()
        test_attributes = {"custom_attr": "test_value"}
        expected_attributes = self._get_expected_attributes(test_attributes)

        with patch.object(metric_sender, '_get_or_create_counter', return_value=mock_counter):
            # Act
            metric_sender.send_metric("test_metric", 5, test_attributes)

            # Assert
            mock_counter.add.assert_called_once_with(5, attributes=expected_attributes)
            mock_logger.debug.assert_called_with(
                f"Metric sent to Azure Monitor: test_metric=5 with attributes: {expected_attributes}"
            )

    @patch('metric_sender_lib.metric_sender.logger')
    def test_send_metric_with_azure_monitor_disabled(self, mock_logger: MagicMock) -> None:
        # Arrange
        metric_sender = MetricSender(self.workflow_id, self.microservice_id, self.health_board, self.peer_service)
        test_attributes = {"custom_attr": "test_value"}
        expected_attributes = self._get_expected_attributes(test_attributes)

        # Act
        metric_sender.send_metric("test_metric", 3, test_attributes)

        # Assert
        mock_logger.info.assert_any_call(
            f"Integration Hub Metric (local log): test_metric=3, attributes: {expected_attributes}"
        )

    @patch('metric_sender_lib.metric_sender.logger')
    def test_send_metric_with_default_value_and_no_attributes(self, mock_logger: MagicMock) -> None:
        # Arrange
        metric_sender = MetricSender(self.workflow_id, self.microservice_id, self.health_board, self.peer_service)
        expected_attributes = self._get_expected_attributes()

        # Act
        metric_sender.send_metric("test_metric")

        # Assert
        mock_logger.info.assert_any_call(
            f"Integration Hub Metric (local log): test_metric=1, attributes: {expected_attributes}"
        )

    @patch('metric_sender_lib.metric_sender.logger')
    @patch.dict('os.environ', {'APPLICATIONINSIGHTS_CONNECTION_STRING': 'test-connection-string'})
    def test_send_metric_with_exception(self, mock_logger: MagicMock) -> None:
        # Arrange
        metric_sender = self._create_metric_sender_with_azure_monitor()
        metric_sender.azure_monitor_enabled = True
        metric_sender._meter = MagicMock()

        with patch.object(metric_sender, '_get_or_create_counter',
                        side_effect=Exception("Counter creation failed")):
            # Act & Assert
            with self.assertRaises(Exception) as context:
                metric_sender.send_metric("test_metric", 1)

            self.assertEqual(str(context.exception), "Counter creation failed")
            mock_logger.error.assert_called_with("Failed to send metric 'test_metric': Counter creation failed")

    @patch('metric_sender_lib.metric_sender.logger')
    def test_send_message_received_metric_scenarios(self, mock_logger: MagicMock) -> None:
        test_cases: List[Dict[str, Any]] = [
            {
                'name': 'with_attributes',
                'attributes': {"message_type": "ADT"}
            },
            {
                'name': 'without_attributes',
                'attributes': None
            }
        ]

        for test_case in test_cases:
            with self.subTest(test_case['name']):
                # Arrange
                metric_sender = MetricSender(self.workflow_id, self.microservice_id, self.health_board, self.peer_service)

                with patch.object(metric_sender, 'send_metric') as mock_send_metric:
                    # Act
                    metric_sender.send_message_received_metric(test_case['attributes'])

                    # Assert
                    mock_send_metric.assert_called_once_with(
                        key="messages_received",
                        value=1,
                        attributes=test_case['attributes']
                    )

    @patch('metric_sender_lib.metric_sender.logger')
    def test_send_message_sent_metric_scenarios(self, mock_logger: MagicMock) -> None:
        test_cases: List[Dict[str, Any]] = [
            {
                'name': 'with_attributes',
                'attributes': {"message_type": "ADT", "ack_code": "AA"}
            },
            {
                'name': 'without_attributes',
                'attributes': None
            }
        ]

        for test_case in test_cases:
            with self.subTest(test_case['name']):
                # Arrange
                metric_sender = MetricSender(self.workflow_id, self.microservice_id, self.health_board, self.peer_service)

                with patch.object(metric_sender, 'send_metric') as mock_send_metric:
                    # Act
                    metric_sender.send_message_sent_metric(test_case['attributes'])

                    # Assert
                    mock_send_metric.assert_called_once_with(
                        key="messages_sent",
                        value=1,
                        attributes=test_case['attributes']
                    )

if __name__ == '__main__':
    unittest.main()
