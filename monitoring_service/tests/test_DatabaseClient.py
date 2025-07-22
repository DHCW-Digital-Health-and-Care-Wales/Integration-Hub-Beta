import json
import unittest
from unittest.mock import Mock, patch

from monitoring_service.database_client import MonitoringDatabaseClient


class TestMonitoringDatabaseClient(unittest.TestCase):

    def setUp(self) -> None:
        self.valid_connection_string = (
            "DRIVER={ODBC Driver 17 for SQL Server};"
            "SERVER=localhost;DATABASE=test;UID=testuser;PWD=testpass;"
        )
        
        self.sample_audit_event = {
            "event_type": "MESSAGE_RECEIVED",
            "workflow_id": "hl7-workflow",
            "microservice_id": "hl7-server",
            "timestamp": "2024-01-15T10:30:00Z",
            "message_content": "MSH|^~\\&|SENDER|RECEIVER|20240115103000||ADT^A01|123456|P|2.5",
            "validation_result": "VALID"
        }
        
        self.mock_connection = Mock()
        self.mock_cursor = Mock()
        self.mock_connection.cursor.return_value = self.mock_cursor
        self.mock_connection.autocommit = False

    def test_init_with_valid_connection_string(self) -> None:
        client = MonitoringDatabaseClient(self.valid_connection_string)
        
        self.assertEqual(client.connection_string, self.valid_connection_string)
        self.assertIsNone(client.connection)

    def test_init_with_empty_connection_string_raises_error(self) -> None:
        with self.assertRaises(ValueError):
            MonitoringDatabaseClient("")
        
        with self.assertRaises(ValueError):
            MonitoringDatabaseClient("   ")
        
        with self.assertRaises(ValueError):
            MonitoringDatabaseClient(None)

    @patch('monitoring_service.database_client.pyodbc')
    def test_connect_success(self, mock_pyodbc: Mock) -> None:
        mock_pyodbc.connect.return_value = self.mock_connection
        
        client = MonitoringDatabaseClient(self.valid_connection_string)
        client.connect()
        
        mock_pyodbc.connect.assert_called_once_with(self.valid_connection_string)
        self.assertEqual(client.connection, self.mock_connection)
        self.assertFalse(client.connection.autocommit)

    @patch('monitoring_service.database_client.pyodbc')
    def test_connect_failure_raises_exception(self, mock_pyodbc: Mock) -> None:
        mock_pyodbc.connect.side_effect = Exception("Connection failed")
        
        client = MonitoringDatabaseClient(self.valid_connection_string)
        
        with self.assertRaises(Exception):
            client.connect()

    def test_disconnect_closes_connection(self) -> None:
        client = MonitoringDatabaseClient(self.valid_connection_string)
        client.connection = self.mock_connection
        
        client.disconnect()
        
        self.mock_connection.close.assert_called_once()
        self.assertIsNone(client.connection)

    def test_disconnect_with_no_connection(self) -> None:
        client = MonitoringDatabaseClient(self.valid_connection_string)
        client.disconnect()  # Should not raise
        self.assertIsNone(client.connection)

    def test_insert_audit_event_success(self) -> None:
        client = MonitoringDatabaseClient(self.valid_connection_string)
        client.connection = self.mock_connection
        
        client.insert_audit_event(self.sample_audit_event)
        
        self.mock_connection.cursor.assert_called_once()
        self.mock_cursor.execute.assert_called_once()
        self.mock_connection.commit.assert_called_once()
        self.mock_cursor.close.assert_called_once()
        
        call_args = self.mock_cursor.execute.call_args
        sql_query = call_args[0][0]
        parameters = call_args[0][1:]
        
        self.assertIn("INSERT INTO [queue].[IntegrationHubEvent]", sql_query)
        self.assertEqual(parameters[0], "INTEGRATION_HUB")
        self.assertEqual(parameters[1], "MESSAGE_RECEIVED")
        
        event_json = parameters[2]
        parsed_event = json.loads(event_json)
        self.assertEqual(parsed_event["workflow_id"], "hl7-workflow")

    def test_insert_audit_event_database_error_rollback(self) -> None:
        client = MonitoringDatabaseClient(self.valid_connection_string)
        client.connection = self.mock_connection
        self.mock_cursor.execute.side_effect = Exception("Database error")
        
        with self.assertRaises(Exception):
            client.insert_audit_event(self.sample_audit_event)
        
        self.mock_connection.rollback.assert_called_once()
        self.mock_cursor.close.assert_called_once()

    def test_insert_exception_event_success(self) -> None:
        exception_event = {
            "event_type": "MESSAGE_FAILED",
            "workflow_id": "hl7-workflow",
            "error_details": "Connection timeout"
        }
        
        client = MonitoringDatabaseClient(self.valid_connection_string)
        client.connection = self.mock_connection
        
        client.insert_exception_event(exception_event)
        
        call_args = self.mock_cursor.execute.call_args
        sql_query = call_args[0][0]
        
        self.assertIn("INSERT INTO [queue].[IntegrationHubException]", sql_query)
        self.mock_connection.commit.assert_called_once()

    def test_context_manager(self) -> None:
        with patch.object(MonitoringDatabaseClient, 'connect') as mock_connect, \
             patch.object(MonitoringDatabaseClient, 'disconnect') as mock_disconnect:
            
            client = MonitoringDatabaseClient(self.valid_connection_string)
            
            with client:
                mock_connect.assert_called_once()
            
            mock_disconnect.assert_called_once()

    def test_event_with_missing_fields_uses_defaults(self) -> None:
        event_no_type = {"workflow_id": "test"}
        
        client = MonitoringDatabaseClient(self.valid_connection_string)
        client.connection = self.mock_connection
        
        client.insert_audit_event(event_no_type)
        
        call_args = self.mock_cursor.execute.call_args
        parameters = call_args[0][1:]
        
        self.assertEqual(parameters[1], "UNKNOWN")  # Default event_type


if __name__ == "__main__":
    unittest.main()