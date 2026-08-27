"""
=============================================================================
Tests Package for Training HL7 Sender
=============================================================================

This package contains unit tests for the training sender components.

RUNNING TESTS:
-------------
From the training_hl7_sender directory:
    cd training_hl7_sender
    uv run pytest tests/ -v

Or run a specific test file:
    uv run pytest tests/test_application.py -v

TESTING PATTERNS USED:
---------------------
1. unittest.mock for mocking external dependencies
2. patch() for replacing functions/classes during tests
3. MagicMock for creating mock objects with any attributes
"""