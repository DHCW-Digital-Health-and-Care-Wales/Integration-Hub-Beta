class Hl7Constants:
    # HL7 Delimiters
    FIELD_SEPARATOR = "|"
    ENCODING_CHARACTERS = "^~\\&"
    PROCESSING_ID_PRODUCTION = "P"

    # ACK message type template
    ACK_MESSAGE_TYPE_FORMAT = "ACK"
    ACK_CODE_ACCEPT = "AA"  # Application Accept

    # Chemocare Authority Codes (MSH.3 values)
    CHEMOCARE_AUTHORITY_CODES = {
        "245": "South_East_Wales_Chemocare",
        "212": "BU_CHEMOCARE_TO_MPI",
        "192": "South_West_Wales_Chemocare",
        "224": "VEL_Chemocare_Demographics_To_MPI",
    }

    # Supported HL7 v2.4 message types for Chemocare
    CHEMOCARE_SUPPORTED_MESSAGE_TYPES = ["A31", "A28", "A40"]
    CHEMOCARE_HL7_VERSION = "2.4"
