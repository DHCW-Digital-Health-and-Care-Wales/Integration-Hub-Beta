import logging

import hl7

logger = logging.getLogger(__name__)


def get_ack_result(response: str) -> bool:
    # Use the lightweight hl7 library (already a dependency) rather than hl7apy,
    # which loads and caches full HL7 schema definitions into memory.
    try:
        msg = hl7.parse(response)

        try:
            msa = msg.segment("MSA")
        except KeyError:
            logger.error("Received a non-ACK message")
            return False

        ack_code = str(msa[1])
        logger.debug(f"ACK Code: {ack_code}")

        if ack_code in ["AA", "CA"]:
            logger.info("Valid ACK received.")
            return True
        else:
            msh = msg.segment("MSH")
            control_id = str(msh[10])
            error = f"Negative ACK received: {ack_code} for: {control_id}"
            logger.error(error)
            return False

    except Exception:
        logger.exception("Exception while parsing ACK message")
        return False
