transformer-base-lib
====================

Shared base library for HL7 transformer applications.

Provides:
- AppConfig for reading environment configuration
- Standard application runner loop (Service Bus receive/process/send)
- Hooks for transformer-specific logic and auditing

Usage
-----
Implement your transformer function that accepts an hl7apy.core.Message and returns a transformed Message. Then wire run_transformer_app from this library in your app's application.py.

