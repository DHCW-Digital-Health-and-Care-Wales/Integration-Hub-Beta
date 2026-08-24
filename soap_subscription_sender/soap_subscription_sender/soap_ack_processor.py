"""Processes the SOAP HTTP response — identical to soap_sender/soap_ack_processor.py.

Duplicated for service independence.
"""
from __future__ import annotations

import logging

from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

logger = logging.getLogger(__name__)

_SUCCESS_CODES = ("AA", "CA")
_HTTP_SUCCESS = (200, 202)


def get_ack_result(status_code: int, response_body: str) -> bool:
    """Evaluate a SOAP HTTP response and return True on success."""
    if status_code not in _HTTP_SUCCESS:
        logger.error("SOAP endpoint returned HTTP %s — treating as failure.", status_code)
        return False

    if "Fault" in response_body:
        logger.error("SOAP fault received:\n%s", response_body[:500])
        return False

    try:
        root = ET.fromstring(response_body)
        for elem in root.iter("Status"):
            status_value = (elem.text or "").strip()
            if status_value in _SUCCESS_CODES:
                logger.info("SOAP ACK received — Status: %s", status_value)
                return True
            else:
                logger.error("SOAP negative ACK — Status: %s", status_value)
                return False
    except ET.ParseError:
        logger.warning("Could not parse SOAP response as XML — body:\n%s", response_body[:200])
    except DefusedXmlException:
        logger.error("Rejected SOAP response containing a malicious XML construct.")
        return False

    logger.info("HTTP %s received with no fault or status element — treating as success.", status_code)
    return True
