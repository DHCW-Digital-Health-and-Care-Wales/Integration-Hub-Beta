import json
import logging
import pyodbc
from typing import Dict, Any, Optional
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

logger = logging.getLogger(__name__)


class MonitoringDatabaseClient:
    
    def __init__(self, connection_string: str, stored_procedure_name: str) -> None:
        if not connection_string or connection_string.strip() == "":
            raise ValueError("Connection string cannot be empty or None")
        if not stored_procedure_name or stored_procedure_name.strip() == "":
            raise ValueError("Stored procedure name must be provided from configuration")
        self.connection_string = connection_string
        self.stored_procedure_name = stored_procedure_name
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

            # Generate XML for the event
            event_xml = self._generate_integration_hub_event_xml(audit_event)
            
            # Map audit event to database fields
            event_category = "INTEGRATION_HUB"
            event_type = self._map_event_type_for_stored_procedure(audit_event)
            
            # Call stored procedure
            cursor.execute(f"""
                EXEC {self.stored_procedure_name}
                @EventCategory = ?, @EventType = ?, @Event = ?
            """, event_category, event_type, event_xml)
            
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

            # Generate XML for exception event
            event_xml = self._generate_integration_hub_event_xml(audit_event)
            
            # Map audit event to database fields
            event_category = "INTEGRATION_HUB"
            event_type = "FESB-E01" 
            
            # Call stored procedure
            cursor.execute(f"""
                EXEC {self.stored_procedure_name}
                @EventCategory = ?, @EventType = ?, @Event = ?
            """, event_category, event_type, event_xml)
            
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

    def _generate_integration_hub_event_xml(self, audit_event: Dict[str, Any]) -> str:
        workflow_id = audit_event.get("workflow_id", "").strip()
        microservice_id = audit_event.get("microservice_id", "").strip()
    
        if not workflow_id or not microservice_id:
            raise ValueError("workflow_id and microservice_id are required for XML generation")
        
        root = Element("IntegrationHubEvent")
        
        # EventData section with core event metadata
        event_data = SubElement(root, "EventData")
        
        timestamp = audit_event.get("timestamp", "")
        if timestamp:
            event_generation_date = SubElement(event_data, "EventGenerationDate")
            event_generation_date.text = timestamp
        
        workflow_instance_id = SubElement(event_data, "WorkflowInstanceId")
        workflow_instance_id.text = f"{workflow_id}_{microservice_id}"
        
        peer_server = SubElement(event_data, "PeerServer")
        peer_server.text = "IntegrationHub"
        
        # EventProcess section with workflow and component information
        event_process = SubElement(root, "EventProcess")
        
        name = SubElement(event_process, "Name")
        name.text = workflow_id
        
        version = SubElement(event_process, "Version")
        version.text = "1.0"
        
        component = SubElement(event_process, "Component")
        component.text = microservice_id
        
        # EventMessage section with payload and context
        event_message = SubElement(root, "EventMessage")
        
        message_content = audit_event.get("message_content", "").strip()
        if message_content:
            payload = SubElement(event_message, "Payload")
            payload.text = message_content
        
        carry_forward_context = SubElement(event_message, "CarryForwardContext")
        carry_forward_context.text = json.dumps(audit_event)
        
        # Convert to formatted XML string
        rough_string = tostring(root, encoding='unicode')
        reparsed = minidom.parseString(rough_string)
        formatted_xml = reparsed.documentElement.toprettyxml(indent="  ")
        
        return f'<?xml version="1.0" encoding="UTF-8"?>\n{formatted_xml}'
    
    def _map_event_type_for_stored_procedure(self, audit_event: Dict[str, Any]) -> str:

        event_type = audit_event.get("event_type", "")
        
        if event_type in ["MESSAGE_FAILED", "VALIDATION_FAILED"]:
            return "FESB-E01"  # Routes to exception table
        elif event_type in ["MESSAGE_RECEIVED", "MESSAGE_PROCESSED", "VALIDATION_SUCCESS"]:
            return "FESB-I01"  # Routes to event and report tables
        else:
            return event_type
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.disconnect()