import pytest
from unittest.mock import MagicMock, patch
import os


class TestGenericHandlerServiceBusIntegration:
    
    @patch.dict(os.environ, {
        'QUEUE_CONNECTION_STRING': 'Endpoint=sb://test.servicebus.windows.net/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=testkey',
        'QUEUE_NAME': 'test-queue'
    })
    @patch('hl7_server.generic_handler.ServiceBusClientFactory')
    @patch('hl7_server.generic_handler.parse_message')
    def test_send_hl7_message_to_service_bus_with_connection_string(self, mock_parse, mock_factory_class):
        from hl7_server.generic_handler import GenericHandler
        
        # Setup mocks
        mock_factory = MagicMock()
        mock_sender_client = MagicMock()
        mock_factory_class.return_value = mock_factory
        mock_factory.create_queue_sender_client.return_value = mock_sender_client
        
        # Mock HL7 message parsing
        mock_msg = MagicMock()
        mock_msg.msh.msh_10.value = "12345"
        mock_msg.msh.msh_9.to_er7.return_value = "ADT^A01"
        mock_parse.return_value = mock_msg
        
        # Create handler
        incoming_message = "MSH|^~\\&|SYSTEM|SENDER|RECEIVER|DESTINATION|20240101120000||ADT^A01|12345|P|2.5"
        handler = GenericHandler(incoming_message)
        
        # Mock the ACK creation
        with patch.object(handler, 'create_ack', return_value="ACK message"):
            result = handler.reply()
        
        # Verify service bus integration with connection string
        mock_factory_class.assert_called_once()
        config = mock_factory_class.call_args[0][0]
        assert config.connection_string == 'Endpoint=sb://test.servicebus.windows.net/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=testkey'
        assert config.service_bus_namespace == ""
        
        mock_factory.create_queue_sender_client.assert_called_once_with("test-queue")
        mock_sender_client.__enter__.assert_called_once()
        mock_sender_client.__exit__.assert_called_once()
        mock_sender_client.__enter__.return_value.send_text_message.assert_called_once_with(incoming_message)

    @patch.dict(os.environ, {
        'SERVICE_BUS_NAMESPACE': 'test-namespace',
        'QUEUE_NAME': 'test-queue'
    })
    @patch('hl7_server.generic_handler.ServiceBusClientFactory')
    @patch('hl7_server.generic_handler.parse_message')
    def test_send_hl7_message_to_service_bus_with_namespace(self, mock_parse, mock_factory_class):
        from hl7_server.generic_handler import GenericHandler
        
        # Setup mocks
        mock_factory = MagicMock()
        mock_sender_client = MagicMock()
        mock_factory_class.return_value = mock_factory
        mock_factory.create_queue_sender_client.return_value = mock_sender_client
        
        # Mock HL7 message parsing
        mock_msg = MagicMock()
        mock_msg.msh.msh_10.value = "67890"
        mock_msg.msh.msh_9.to_er7.return_value = "ORU^R01"
        mock_parse.return_value = mock_msg
        
        # Create handler
        incoming_message = "MSH|^~\\&|LAB|SENDER|RECEIVER|DESTINATION|20240101130000||ORU^R01|67890|P|2.5"
        handler = GenericHandler(incoming_message)
        
        # Mock the ACK creation
        with patch.object(handler, 'create_ack', return_value="ACK message"):
            result = handler.reply()
        
        # Verify service bus integration with namespace
        mock_factory_class.assert_called_once()
        config = mock_factory_class.call_args[0][0]
        assert config.connection_string == ""
        assert config.service_bus_namespace == "test-namespace"
        
        mock_factory.create_queue_sender_client.assert_called_once_with("test-queue")
        mock_sender_client.__enter__.assert_called_once()
        mock_sender_client.__exit__.assert_called_once()
        mock_sender_client.__enter__.return_value.send_text_message.assert_called_once_with(incoming_message)

    @patch.dict(os.environ, {
        'QUEUE_CONNECTION_STRING': 'test-connection-string',
        'QUEUE_NAME': 'test-queue'
    })
    @patch('hl7_server.generic_handler.ServiceBusClientFactory')
    @patch('hl7_server.generic_handler.parse_message')
    def test_service_bus_send_failure_raises_exception(self, mock_parse, mock_factory_class):
        from hl7_server.generic_handler import GenericHandler
        
        # Setup mocks
        mock_factory = MagicMock()
        mock_sender_client = MagicMock()
        mock_factory_class.return_value = mock_factory
        mock_factory.create_queue_sender_client.return_value = mock_sender_client
        
        # Make the sender raise an exception
        mock_sender_client.__enter__.return_value.send_text_message.side_effect = Exception("Service Bus error")
        
        # Mock HL7 message parsing
        mock_msg = MagicMock()
        mock_msg.msh.msh_10.value = "ERROR123"
        mock_msg.msh.msh_9.to_er7.return_value = "ADT^A01"
        mock_parse.return_value = mock_msg
        
        # Create handler with required message parameter
        incoming_message = "test hl7 message"
        handler = GenericHandler(incoming_message)
        
        # Verify service bus errors
        with pytest.raises(Exception, match="Service Bus error"):
            handler.reply()
        
        # Verify service bus was attempted
        mock_sender_client.__enter__.return_value.send_text_message.assert_called_once_with(incoming_message)