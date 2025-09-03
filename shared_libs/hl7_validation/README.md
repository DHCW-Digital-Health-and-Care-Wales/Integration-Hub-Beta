# HL7 Validation Library

A Python library for validating HL7 v2 messages through XML Schema validation. This library converts HL7 v2 ER7 (pipe-delimited) messages to HL7 v2 XML format and validates them against XML Schema Definition (XSD) files.

## Purpose

This library helps healthcare integration teams validate HL7 v2 messages against specific XML schemas. It supports multiple integration flows with flow-specific validation rules and schemas.

## Schema Requirements

Each flow directory should contain:

1. **Structure XSDs**: Named by trigger event (e.g., `A05.xsd`, `A39.xsd`)
2. **Base HL7 XSDs**: Version-specific base schemas (e.g., `2_5_fields.xsd`, `2_5_segments.xsd`, `2_5_types.xsd`)
3. No fallback configuration file is required; built-in mappings are used for ADT triggers where applicable.

When adding new flows or message types:

1. Create a new directory under `hl7_validation/resources/`
2. Add the appropriate HL7 base XSDs for your HL7 version
3. Add structure XSDs named by trigger event
4. No need to update any fallback configuration; ensure required structure XSDs exist.
5. Add tests for your new schemas

No code changes are required - the library automatically discovers new schema mappings.

## Installation

```bash
pip install hl7_validation_lib
```

Or using uv:
```bash
uv add hl7_validation_lib
```

## Quick Start

### Basic Validation

```python
from hl7_validation import validate_er7_with_flow

# Your HL7 v2 ER7 message
er7_message = "\r".join([
    "MSH|^~\\&|SENDER|FACILITY|RECEIVER|FACILITY|20250101010101||ADT^A05^ADT_A05|MSG123|P|2.5",
    "EVN|A05|20250101010101",
    "PID|||123456^^^MR||DOE^JOHN||19800101|M",
    "PV1||I",
])

# Validate for a specific flow (e.g., "phw")
try:
    validate_er7_with_flow(er7_message, "phw")
    print("Message is valid!")
except XmlValidationError as e:
    print(f"Validation failed: {e}")
```

### Supported Flows

The library supports multiple integration flows, each with their own set of HL7 schemas:

- `phw` - Patient Health Workflow
- `chemo` - Chemotherapy
- `paris` - Paris integration
- `pims` - Patient Information Management System

#### Convert ER7 to XML

```python
from hl7_validation.convert import er7_to_hl7v2xml
from hl7_validation import get_schema_xsd_path_for

# Get the schema path for your flow and message type
xsd_path = get_schema_xsd_path_for("phw", "A05")

# Convert ER7 to XML
xml_output = er7_to_hl7v2xml(er7_message, structure_xsd_path=xsd_path)
print(xml_output)
```

#### Direct XML Validation

```python
from hl7_validation import validate_xml

# If you already have HL7 XML
xml_content = "<ADT_A05>...</ADT_A05>"
xsd_path = "/path/to/schema.xsd"

validate_xml(xml_content, xsd_path)  # Raises XmlValidationError if invalid
```

#### Explore Available Schemas

```python
from hl7_validation import list_schema_groups, list_schemas_for_group

# List all available flows
flows = list_schema_groups()
print("Available flows:", flows)

# List schemas for a specific flow
phw_schemas = list_schemas_for_group("phw")
print("PHW schemas:", phw_schemas)
```

## Message Structure Detection

The library automatically detects message structure from the MSH segment:

1. **Primary**: Uses `MSH-9.3` (structure field) - e.g., `ADT^A05^ADT_A05` → uses `ADT_A05.xsd`
2. **Built-in mapping**: If `MSH-9.3` is missing, uses `MSH-9.2` (trigger) with built-in ADT mappings for HL7 v2.4 and below:
   - `ADT A28` → `ADT_A05`
   - `ADT A31` → `ADT_A05`
   - `ADT A40` → `ADT_A39`

Example of fallback usage:
```python
# Message with missing structure
er7_missing_structure = "\r".join([
    "MSH|^~\\&|SENDER|FACILITY|RECEIVER|FACILITY|20250101010101||ADT^A31|MSG123|P|2.5",
    "PID|||123456^^^MR||DOE^JOHN",
])

# Will use built-in mapping: ADT A31 → ADT_A05 for 'phw' flow
validate_er7_with_flow(er7_missing_structure, "phw")
```

## Error Handling

The library provides clear error messages:

```python
from hl7_validation import validate_er7_with_flow, XmlValidationError

try:
    validate_er7_with_flow(er7_message, "phw")
except XmlValidationError as e:
    print(f"HL7 validation error: {e}")
except ValueError as e:
    print(f"Configuration error: {e}")
```

Common error types:
- `XmlValidationError`: Message doesn't conform to schema
- `ValueError`: Invalid flow name or missing schema mapping

## Dependencies

- `hl7apy>=1.3.5` - For ER7 message parsing
- `xmlschema>=3.4.3` - For XML Schema validation
- `defusedxml>=0.7.1` - For secure XML parsing
- `Python>=3.13`

## Examples

See the `tests/` directory for comprehensive examples including:
- ADT A05 messages (patient admissions)
- ADT A39 messages (patient merges)
- Multi-identifier repetitions
- Structure detection and fallback scenarios