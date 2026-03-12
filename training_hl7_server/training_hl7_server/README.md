This file is an HL7 ACK message builder: it creates acknowledgment messages to send back after receiving an HL7 message.

- The module purpose is declared at ack_builder.py.
- The main class is ack_builder.py, with two methods.

1. ack_builder.py
- Builds a full, standards-compliant ACK using strict validation (ack_builder.py, ack_builder.py).
- Fills MSH header fields, including swapping sender/receiver from the original message (ack_builder.py, ack_builder.py, ack_builder.py, ack_builder.py).
- Keeps the original trigger event and version (ack_builder.py, ack_builder.py).
- Sets acknowledgment code and control ID in MSA (ack_builder.py, ack_builder.py), optionally adds error text (ack_builder.py).
- Returns a ready-to-send Message object (ack_builder.py).

2. ack_builder.py
- Builds a fallback error ACK with tolerant validation (ack_builder.py, ack_builder.py).
- Uses UNKNOWN for most MSH routing/type fields (ack_builder.py, ack_builder.py, ack_builder.py, ack_builder.py, ack_builder.py, ack_builder.py) and hardcodes HL7 version 2.5 (ack_builder.py).
- Still includes the passed control ID in MSA-2 (ack_builder.py).
- Returns the fallback ACK (ack_builder.py).

One thing to note: in the minimal ACK, MSH-10 is set to UNKNOWN (ack_builder.py) while MSA-2 uses the actual control ID (ack_builder.py). That may be intentional, but some receivers expect those to align.

Experimental change