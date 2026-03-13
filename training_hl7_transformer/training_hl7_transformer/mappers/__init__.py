"""MSH Mapper Package.

This package contains mappers for transforming individual HL7 segments.
Each mapper follows a similar pattern:
1. Takes the original message and new message as input
2. Copies fields from original to new, applying transformations
3. Returns any transformation details for logging/auditing
"""
