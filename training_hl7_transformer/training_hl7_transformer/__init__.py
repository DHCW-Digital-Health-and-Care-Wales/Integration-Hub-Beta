
"""Training HL7 Transformer Package.

This package contains a minimal HL7 message transformer for training purposes.
It demonstrates the ingress -> transform -> egress queue pattern used throughout
the Integration Hub project.

The transformer:
1. Reads HL7 messages from an ingress queue (training-transformer-ingress)
2. Parses the message and transforms the MSH segment
3. Publishes the transformed message to an egress queue (training-egress)

This is a simplified version of the production transformers that doesn't
use logging/metrics libraries. Use print() statements for debugging.
"""
