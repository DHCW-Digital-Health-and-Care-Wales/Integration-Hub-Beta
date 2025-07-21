import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional
from xml.dom import minidom

from hl7apy.core import Message, Segment, Field, Component, SubComponent


class Hl7XmlConverter:


    def __init__(self):
        pass

    def convert_to_xml(self, parsed_message: Message) -> str:
        try:
            # Get message type from MSH segment
            message_type = self._get_message_type(parsed_message)

            # Create root element with HL7 v2xml namespace
            root = ET.Element(message_type)
            root.set('xmlns', 'urn:hl7-org:v2xml')

            # Process all segments in the message
            for segment in parsed_message.children:
                segment_element = self._convert_segment_to_xml(segment)
                root.append(segment_element)

            # Convert to pretty formatted XML string
            return self._prettify_xml(root)

        except Exception as e:
            raise ValueError(f"Failed to convert HL7 message to XML: {str(e)}")

    def _get_message_type(self, message: Message) -> str:
        try:
            msh_segment = message.msh
            message_type_field = msh_segment.msh_9

            if hasattr(message_type_field, 'msh_9_1') and message_type_field.msh_9_1.value:
                message_code = message_type_field.msh_9_1.value
                trigger_event = ""
                if hasattr(message_type_field, 'msh_9_2') and message_type_field.msh_9_2.value:
                    trigger_event = message_type_field.msh_9_2.value
                return f"{message_code}_{trigger_event}" if trigger_event else message_code
            else:
                # Fallback to parsing the entire field value
                message_type_value = message_type_field.value or ""
                parts = message_type_value.split("^")
                if len(parts) >= 2:
                    return f"{parts[0]}_{parts[1]}"
                return parts[0] if parts else "UNKNOWN_MESSAGE"

        except Exception:
            return "UNKNOWN_MESSAGE"

    def _convert_segment_to_xml(self, segment: Segment) -> ET.Element:
        segment_element = ET.Element(segment.name)

        field_index = 1
        for field in segment.children:
            field_element = self._convert_field_to_xml(field, segment.name, field_index)
            segment_element.append(field_element)
            field_index += 1

        return segment_element

    def _convert_field_to_xml(self, field: Field, segment_name: str, field_index: int) -> ET.Element:
        """
        Convert an HL7 field to XML element.

        Args:
            field: HL7 field to convert
            segment_name: Name of the parent segment
            field_index: Index of the field within the segment

        Returns:
            XML element representing the field
        """
        field_name = f"{segment_name}.{field_index}"
        field_element = ET.Element(field_name)

        # Check if field has a direct value and no children
        field_value = self._get_value_as_string(field)
        if field_value and not field.children:
            component_element = ET.SubElement(field_element, f"{field_name}.1")
            component_element.text = self._escape_xml_text(field_value)
        else:
            # Handle field with components
            component_index = 1
            for component in field.children:
                component_element = self._convert_component_to_xml(
                    component, field_name, component_index
                )
                field_element.append(component_element)
                component_index += 1

        return field_element

    def _convert_component_to_xml(self, component: Component, field_name: str, component_index: int) -> ET.Element:
        """
        Convert an HL7 component to XML element.

        Args:
            component: HL7 component to convert
            field_name: Name of the parent field
            component_index: Index of the component within the field

        Returns:
            XML element representing the component
        """
        component_name = f"{field_name}.{component_index}"
        component_element = ET.Element(component_name)

        # Check if component has a direct value and no children
        component_value = self._get_value_as_string(component)
        if component_value and not component.children:
            component_element.text = self._escape_xml_text(component_value)
        else:
            # Handle component with subcomponents
            subcomponent_index = 1
            for subcomponent in component.children:
                subcomponent_element = self._convert_subcomponent_to_xml(
                    subcomponent, component_name, subcomponent_index
                )
                component_element.append(subcomponent_element)
                subcomponent_index += 1

        return component_element

    def _convert_subcomponent_to_xml(
        self, subcomponent: SubComponent, component_name: str, subcomponent_index: int
    ) -> ET.Element:
        """
        Convert an HL7 subcomponent to XML element.

        Args:
            subcomponent: HL7 subcomponent to convert
            component_name: Name of the parent component
            subcomponent_index: Index of the subcomponent within the component

        Returns:
            XML element representing the subcomponent
        """
        subcomponent_name = f"{component_name}.{subcomponent_index}"
        subcomponent_element = ET.Element(subcomponent_name)

        subcomponent_value = self._get_value_as_string(subcomponent)
        if subcomponent_value:
            subcomponent_element.text = self._escape_xml_text(subcomponent_value)

        return subcomponent_element

    def _get_value_as_string(self, hl7_element) -> str:
        """
        Safely extract string value from HL7apy element.

        Args:
            hl7_element: HL7apy element (Field, Component, SubComponent, etc.)

        Returns:
            String representation of the element's value
        """
        if not hl7_element:
            return ""

        try:
            if hasattr(hl7_element, 'value') and hl7_element.value is not None:
                # For HL7apy objects, convert value to string
                value = hl7_element.value
                if hasattr(value, 'value'):
                    # Nested HL7apy object
                    return str(value.value) if value.value is not None else ""
                else:
                    return str(value)
            return ""
        except Exception:
            return ""

    def _escape_xml_text(self, text) -> str:
        """
        Escape special characters for XML content.

        Args:
            text: Text to escape (can be string or HL7apy object)

        Returns:
            XML-escaped text
        """
        if not text:
            return ""

        # Convert HL7apy objects to string
        if hasattr(text, 'value'):
            text_str = str(text.value) if text.value is not None else ""
        else:
            text_str = str(text)

        if not text_str:
            return ""

        # Replace XML special characters
        text_str = text_str.replace("&", "&amp;")
        text_str = text_str.replace("<", "&lt;")
        text_str = text_str.replace(">", "&gt;")
        text_str = text_str.replace('"', "&quot;")
        text_str = text_str.replace("'", "&apos;")

        return text_str

    def _prettify_xml(self, element: ET.Element) -> str:
        # Convert to string
        rough_string = ET.tostring(element, encoding='unicode')

        # Parse and prettify using minidom
        reparsed = minidom.parseString(rough_string)
        pretty_xml = reparsed.toprettyxml(indent="    ")

        # Remove the XML declaration and empty lines
        lines = pretty_xml.split('\n')
        lines = [line for line in lines if line.strip() and not line.startswith('<?xml')]

        return '\n'.join(lines)
