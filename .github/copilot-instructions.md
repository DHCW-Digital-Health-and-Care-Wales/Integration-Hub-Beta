---
description: "Python coding conventions and guidelines"
applyTo: "**/*.py"
---

# Python Coding Conventions

## Project Context

Integration Hub is a cloud-native, event-driven microservices platform for secure HL7 message ingestion,
transformation, and delivery across NHS Wales systems. Services are Python 3.13-based and communicate via
Azure Service Bus, with shared libraries in `shared_libs/` providing common capabilities.

## Python Instructions

1. Prioritize correctness and clear error handling (validate inputs, handle edge cases, and raise explicit errors).
2. Prefer reuse of utilities from `shared_libs/` over duplicating functionality.
3. For HL7 mappers and transformers, mirror the structure and style of existing components (e.g. in `hl7_pims_transformer`, `hl7_chemo_transformer`, `hl7_phw_transformer`)
4. Keep module-level behavior import-safe (avoid side effects at import time unless required).
5. Ensure functions have descriptive names and include type hints.
6. Use the `typing` module for type annotations (e.g., `List[str]`, `Dict[str, int]`).
7. Break down complex functions into smaller, more manageable functions.
8. Add or update tests for new or changed code to keep coverage of critical paths.

## General Instructions

- Always prioritize readability and clarity.
- For algorithm-related code, include explanations of the approach used.
- Write code with good maintainability practices, including comments on why certain design decisions were made.
- Handle edge cases and write clear exception handling.
- For libraries or external dependencies, mention their usage and purpose in comments.
- Use consistent naming conventions and follow language-specific best practices.
- Write concise, efficient, and idiomatic code that is also easily understandable.
- Avoid adding new dependencies unless there is a clear, documented need.

## Code Style and Formatting

- Follow the **PEP 8** style guide for Python.
- Maintain proper indentation (use 4 spaces for each level of indentation).
- Ensure lines do not exceed 120 characters.
- Use blank lines to separate functions, classes, and code blocks where appropriate.

## Tooling and Environment

- Use `uv` for dependency management and virtual environments; do not use `pip`, `poetry`, or `pipenv` directly.
- Target Python 3.13+ as defined in `pyproject.toml` files.
- Add new dependencies to `pyproject.toml` (and the appropriate dependency group) rather than `requirements.txt`.
- Prefer running checks, including lint/type tools via `uv run` or `uv tool run` for consistency with CI.

## Server Component Rules

- Do not introduce thread pools or asynchronous request handling for message processing unless explicitly requested.
- Sending to Service Bus should happen async inside the handler; ACK should only be returned after the message is sent.

## Anti Patterns to Avoid

- Do NOT hardcode configuration values; use `app_config.py` patterns.
- Do NOT use `print()` for logging unless in a training context; use the `event_logger_lib` from `shared_libs`.

## Testing

- Use Python `unittest` only; do not introduce `pytest`.
- Keep tests in a top-level `tests/` directory and name files `test_*.py`.
- Prefer `unittest.TestCase` with `unittest.mock` for mocking.
- Default test run command: `uv run python -m unittest discover tests`.

## Edge Cases and Testing

- Always include test cases for critical paths of the application.
- Account for common edge cases like empty inputs, invalid data types, and large datasets.
- Include comments for edge cases and the expected behavior in those cases.
