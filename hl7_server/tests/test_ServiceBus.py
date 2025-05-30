import pytest
from unittest.mock import MagicMock, patch
from hl7server.ServiceBusConfig import ServiceBusConfig
from hl7server.ServiceBusMessageSender import ServiceBusMessageSender
from azure.servicebus import ServiceBusMessage


TEST_CONN_STRING = "Endpoint=sb://test.servicebus.windows.net/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=testkey"

@pytest.fixture
def mock_env_local(monkeypatch):
    monkeypatch.setenv("QUEUE_NAME", "test-queue")
    monkeypatch.setenv("QUEUE_CONNECTION_STRING", TEST_CONN_STRING)

@pytest.fixture
def mock_env_cloud(monkeypatch):
    monkeypatch.setenv("QUEUE_NAME", "test-queue")
    monkeypatch.setenv("SERVICE_BUS_NAMESPACE", "test-namespace")

class TestServiceBusConfig:
    def test_local_config(self, mock_env_local):
        config = ServiceBusConfig.from_env()
        assert config.queue_name == "test-queue"
        assert config.connection_string == TEST_CONN_STRING
        assert config.namespace is None
        assert config.is_local_setup() is True

    def test_cloud_config(self, mock_env_cloud):
        config = ServiceBusConfig.from_env()
        assert config.queue_name == "test-queue"
        assert config.connection_string is None
        assert config.namespace == "test-namespace"
        assert config.is_local_setup() is False

    def test_missing_required_env(self, monkeypatch):
        monkeypatch.delenv("QUEUE_NAME", raising=False)
        with pytest.raises(ValueError, match="QUEUE_NAME environment variable is required"):
            ServiceBusConfig.from_env()

    def test_missing_connection_details(self, monkeypatch):
        monkeypatch.setenv("QUEUE_NAME", "test-queue")
        with pytest.raises(ValueError, match="Either QUEUE_CONNECTION_STRING or SERVICE_BUS_NAMESPACE must be provided"):
            ServiceBusConfig.from_env()


class TestServiceBusMessageSender:
    @patch('hl7server.ServiceBusMessageSender.ServiceBusClient')
    def test_send_message_local(self, mock_service_bus_client, mock_env_local):
        # Setup mocks
        mock_sender = MagicMock()
        mock_client_instance = MagicMock()
        mock_client_instance.__enter__.return_value = mock_client_instance
        mock_client_instance.__exit__.return_value = None
        mock_client_instance.get_queue_sender.return_value.__enter__.return_value = mock_sender
        mock_client_instance.get_queue_sender.return_value.__exit__.return_value = None
        
        mock_service_bus_client.from_connection_string.return_value = mock_client_instance
        
        # Create sender and send message
        sender = ServiceBusMessageSender()
        sender.send_message("test message")

        # Assert
        mock_service_bus_client.from_connection_string.assert_called_once_with(
            conn_str=TEST_CONN_STRING
        )
        mock_client_instance.get_queue_sender.assert_called_once_with(queue_name="test-queue")
        mock_sender.send_messages.assert_called_once()
        
        # Verify the message content
        sent_message = mock_sender.send_messages.call_args[0][0]
        assert isinstance(sent_message, ServiceBusMessage)
        body_content = b''.join(sent_message.body)
        assert body_content.decode() == "test message"

    @patch('hl7server.ServiceBusMessageSender.ServiceBusClient')
    @patch('hl7server.ServiceBusMessageSender.DefaultAzureCredential')
    def test_send_message_cloud(self, mock_credential, mock_service_bus_client, mock_env_cloud):
        
        # Setup mocks
        mock_sender = MagicMock()
        mock_client_instance = MagicMock()
        mock_client_instance.__enter__.return_value = mock_client_instance
        mock_client_instance.__exit__.return_value = None
        mock_client_instance.get_queue_sender.return_value.__enter__.return_value = mock_sender
        mock_client_instance.get_queue_sender.return_value.__exit__.return_value = None
        
        mock_service_bus_client.return_value = mock_client_instance
        mock_credential_instance = MagicMock()
        mock_credential.return_value = mock_credential_instance
        
        # Create sender and send message
        sender = ServiceBusMessageSender()
        sender.send_message("test message")

        # Assert
        mock_credential.assert_called_once()
        mock_service_bus_client.assert_called_once_with(
            fully_qualified_namespace="test-namespace.servicebus.windows.net",
            credential=mock_credential_instance
        )
        mock_client_instance.get_queue_sender.assert_called_once_with(queue_name="test-queue")
        mock_sender.send_messages.assert_called_once()
        
        # Verify the message content
        sent_message = mock_sender.send_messages.call_args[0][0]
        assert isinstance(sent_message, ServiceBusMessage)
        body_content = b''.join(sent_message.body)
        assert body_content.decode() == "test message"    