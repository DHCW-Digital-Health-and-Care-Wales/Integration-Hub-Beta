import json
import logging
import pyodbc
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class MonitoringDatabaseClient:
    
    def __init__(self, connection_string: str):
        if not connection_string or connection_string.strip() == "":
            raise ValueError("Connection string cannot be empty or None")
        self.connection_string = connection_string
        self.connection: Optional[pyodbc.Connection] = None
    
    def connect(self) -> None:
        try:
            self.connection = pyodbc.connect(self.connection_string)
            logger.info("Database connection established")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
    
    def disconnect(self) -> None:
        if self.connection:
            self.connection.close()
            self.connection = None
            logger.info("Database connection closed")
    
    def insert_audit_event(self, audit_event: Dict[str, Any]) -> None:
        if not self.connection:
            self.connect()
        
        cursor = None
        try:
            cursor = self.connection.cursor()
            
            # Map audit event to database fields
            event_category = "INTEGRATION_HUB"
            event_type = audit_event.get("event_type", "UNKNOWN")
            event_json = json.dumps(audit_event)
            
            # Insert into queue table
            cursor.execute("""
                INSERT INTO [queue].[IntegrationHubEvent]
                ([EventCategory], [EventType], [Event])
                VALUES (?, ?, ?)
            """, event_category, event_type, event_json)
            
            self.connection.commit()
            logger.debug(f"Inserted audit event: {event_type}")
            
        except Exception as e:
            logger.error(f"Failed to insert audit event: {e}")
            if self.connection:
                self.connection.rollback()
            raise
        finally:
            if cursor:
                cursor.close()
    
    def insert_exception_event(self, audit_event: Dict[str, Any]) -> None:
        if not self.connection:
            self.connect()
        
        try:
            cursor = self.connection.cursor()
            
            # Map audit event to database fields
            event_category = "INTEGRATION_HUB"
            event_type = audit_event.get("event_type", "UNKNOWN")
            event_json = json.dumps(audit_event)
            
            # Insert into exception queue table
            cursor.execute("""
                INSERT INTO [queue].[IntegrationHubException]
                ([EventCategory], [EventType], [Event])
                VALUES (?, ?, ?)
            """, event_category, event_type, event_json)
            
            self.connection.commit()
            logger.debug(f"Inserted exception event: {event_type}")
            
        except Exception as e:
            logger.error(f"Failed to insert exception event: {e}")
            if self.connection:
                self.connection.rollback()
            raise
        finally:
            if cursor:
                cursor.close()
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.disconnect()