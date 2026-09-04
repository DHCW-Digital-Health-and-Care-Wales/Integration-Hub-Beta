from pydantic import BaseModel, Field


class HL7Message(BaseModel):
    """Request body for the ``POST /hl7MessageReceiver`` endpoint.

    ``messageContent`` carries either a raw ER7 (pipe-and-hat) HL7 message or an
    HL7 v2 XML document (namespace ``urn:hl7-org:v2xml``).
    """

    messageContent: str = Field(..., description="Raw ER7 HL7 message or HL7 v2 XML document.")
