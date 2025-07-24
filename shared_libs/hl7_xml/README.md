# HL7 XML

Package for HL7v2 serialization to XML.

Supports Hl7v2 structures from [hl7Apy](https://crs4.github.io/hl7apy/) library.

## Usage

```Python
from hl7_xml.hl7_to_xml import mapHl7toXml

message: hl7apy.core.Message = (...)
xml =  result = mapHl7toXml(message)
```

## Development

Install dependencies:
```sh
uv sync
```

Run unit tests:

```sh
uv run python -m unittest discover tests
```