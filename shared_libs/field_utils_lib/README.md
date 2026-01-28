# Field Utils Library

Shared utilities for safely reading and setting nested HL7 fields using hl7apy, enabling robust HL7 message transformations across multiple services.

## Overview

Working with nested HL7 field structures can be error-prone when fields are missing or have unexpected structures. This library provides safe accessor functions that handle missing fields gracefully and support both dot-separated paths and bracket notation for field repetitions.

All Integration Hub transformers (PHW, Chemo, PIMS) use these utilities to safely extract and manipulate HL7 data without extensive null checking.

## Features

- **Safe field access**: Returns empty strings instead of raising exceptions for missing fields
- **Dot notation**: Access nested fields like `pid_5.xpn_1.fn_1` (Patient Name → Family Name → Surname)
- **Bracket notation**: Handle field repetitions like `pid_13[1].xtn_1` (second phone number → telephone number)
- **Bidirectional operations**: Both read (`get_hl7_field_value`) and write (`set_nested_field`) support

## Usage

### Reading Fields

```python
from field_utils_lib import get_hl7_field_value

# Get simple field
nhs_number = get_hl7_field_value(pid_segment, "pid_3.cx_1")

# Get nested field (family name)
family_name = get_hl7_field_value(pid_segment, "pid_5.xpn_1.fn_1")

# Get field with repetition (second phone number)
phone = get_hl7_field_value(pid_segment, "pid_13[1].xtn_1")

# Missing fields return empty string instead of exceptions
date_of_death = get_hl7_field_value(pid_segment, "pid_29.ts_1")  # Returns "" if not present
```

### Setting/Copying Fields

```python
from field_utils_lib import set_nested_field

# Copy field from source to target
success = set_nested_field(source_pid, target_pid, "pid_3.cx_1")  # Copy NHS number

# Works with nested paths
set_nested_field(source_pid, target_pid, "pid_5.xpn_1.fn_1")  # Copy family name

# Returns True if successful, False if source field missing
```

## Development

### Dependencies

- [uv](https://docs.astral.sh/uv/) - Python package and project manager
- macOS: `brew install uv`
- Other platforms: See [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/)

### Build / checks

In the [field_utils_lib](.) folder, to create a virtual environment and install project dependencies:

```bash
uv sync
```

Run code quality checks:

```bash
uv run ruff check
uv run bandit field_utils_lib/**/*.py tests/**/*.py
uv run mypy --ignore-missing-imports field_utils_lib/**/*.py tests/**/*.py
```

Run unit tests:

```bash
uv run python -m unittest discover tests
```
