"""
=============================================================================
Training HL7 Sender - Week 3 Training
=============================================================================

A minimal HL7 sender that demonstrates the pattern of:
1. Receiving messages from an Azure Service Bus queue
2. Sending them via MLLP (Minimal Lower Layer Protocol) to a destination
3. Validating ACK responses
4. Handling graceful shutdown with signal handlers

This completes the full HL7 integration pipeline:
  Server (Week 1) → Transformer (Week 2) → Sender (Week 3) → Mock Receiver

SESSION ID EXPLANATION:
----------------------
Session IDs ensure messages are processed in order within a workflow.
Different session IDs are used at different stages:

  Server → Transformer:  session = "training-session"
  Transformer → Sender:  session = "training"

Why different? Each queue has its own session namespace. The session ID
is used to group related messages within a single queue. When crossing
queue boundaries (transformer egress → sender ingress), a new session
scope begins, so we use a simpler ID for clarity.
"""