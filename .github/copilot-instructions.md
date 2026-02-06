---
description: "Python coding conventions and guidelines"
applyTo: "**/*.py"
---

# Python Coding Conventions

## Python Instructions

- Ensure functions have descriptive names and include type hints.
- Use the `typing` module for type annotations (e.g., `List[str]`, `Dict[str, int]`).
- Break down complex functions into smaller, more manageable functions.
- Prefer reuse of utilities from `shared_libs/` over duplicating functionality.
- Keep module-level behavior import-safe (avoid side effects at import time unless required).

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

## Testing

- Use Python `unittest` only; do not introduce `pytest`.
- Keep tests in a top-level `tests/` directory and name files `test_*.py`.
- Prefer `unittest.TestCase` with `unittest.mock` for mocking.
- Default test run command: `uv run python -m unittest discover tests`.

## Edge Cases and Testing

- Always include test cases for critical paths of the application.
- Account for common edge cases like empty inputs, invalid data types, and large datasets.
- Include comments for edge cases and the expected behavior in those cases.
