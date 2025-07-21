import os
import logging
from typing import Dict, Optional, List, Tuple
from pathlib import Path
from lxml import etree

logger = logging.getLogger(__name__)


class XMLSchemaValidator:
    def __init__(self, schemas_dir: Optional[str] = None):
        if schemas_dir is None:
            schemas_dir = os.path.join(os.path.dirname(__file__), 'schemas')

        self.schemas_dir = schemas_dir
        self.schema_map: Dict[str, etree.XMLSchema] = {}
        self._load_schemas()

    def _load_schemas(self) -> None:
        try:
            schema_files = list(Path(self.schemas_dir).glob('*.xsd'))

            if not schema_files:
                logger.warning(f"No XSD schemas found in {self.schemas_dir}")
                return

            logger.info(f"Loading {len(schema_files)} schema files from {self.schemas_dir}")

            for schema_path in schema_files:
                schema_name = schema_path.name
                try:
                    # Parse the schema file
                    schema_doc = etree.parse(str(schema_path))
                    schema = etree.XMLSchema(schema_doc)
                    self.schema_map[schema_name] = schema
                    logger.info(f"Successfully loaded schema: {schema_name}")
                except Exception as e:
                    logger.error(f"Failed to load schema {schema_name}: {str(e)}")

            logger.info(f"Successfully loaded {len(self.schema_map)} schemas")
        except Exception as e:
            logger.error(f"Error loading schemas: {str(e)}")

    def get_available_schemas(self) -> List[str]:
        return list(self.schema_map.keys())

    def validate(self, xml_string: str, schema_name: Optional[str] = None) -> Tuple[bool, List[str]]:
        """
        Validate an XML string against a schema.

        Args:
            xml_string: The XML string to validate
            schema_name: The name of the schema file to use for validation.
                        If None, defaults to 'ADT_ALL_2.5.xsd'

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        # Validate input parameters
        if not xml_string or not xml_string.strip():
            errors.append("XML string cannot be empty or whitespace")
            return False, errors

        # Default to ADT_ALL_2.5.xsd if no schema specified
        if schema_name is None:
            schema_name = "ADT_ALL_2.5.xsd"

        # Check if the requested schema exists
        if schema_name not in self.schema_map:
            available_schemas = ", ".join(self.get_available_schemas())
            errors.append(f"Schema '{schema_name}' not found. Available schemas: {available_schemas}")
            return False, errors

        try:
            # Parse the XML string
            xml_doc = etree.fromstring(xml_string.encode('utf-8'))
            logger.debug(f"Successfully parsed XML string")

            # Get the schema for validation
            schema = self.schema_map[schema_name]

            # Validate the XML document against the schema
            if schema.validate(xml_doc):
                logger.info(f"XML validation successful using schema: {schema_name}")
                return True, []
            else:
                # Collect validation errors
                for error in schema.error_log:
                    error_message = f"Line {error.line}: {error.message}"
                    errors.append(error_message)
                    logger.warning(f"Validation error: {error_message}")

                logger.error(f"XML validation failed using schema: {schema_name}")
                return False, errors

        except etree.XMLSyntaxError as e:
            error_message = f"XML syntax error: {str(e)}"
            errors.append(error_message)
            logger.error(error_message)
            return False, errors

        except Exception as e:
            error_message = f"Unexpected error during validation: {str(e)}"
            errors.append(error_message)
            logger.error(error_message)
            return False, errors
