"""Processes the SOAP HTTP response and returns a success boolean.

Mirrors ``ack_processor.py`` in ``hl7_sender`` — same bool-return contract so
``application.py`` can use it identically to drive Service Bus ACK/abandon.

Success criteria (returns True):
  - HTTP 200 or 202 AND no SOAP Fault element in body
  - Additionally looks for <Status>AA</Status> or <Status>CA</Status> in the body

Failure (returns False):
  - HTTP 4xx or 5xx
  - HTTP 200/202 but body contains a SOAP Fault element
  - HTTP 200/202 but body contains a non-AA/CA Status element
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

_SUCCESS_CODES = ("AA", "CA")
_HTTP_SUCCESS = (200, 202)


def get_ack_result(status_code: int, response_body: str) -> bool:
    """Evaluate a SOAP HTTP response and return True on success.

    Args:
        status_code: HTTP response status code.
        response_body: Raw response body string.

    Returns:
        True if the response indicates successful message acceptance.
    """
    if status_code not in _HTTP_SUCCESS:
        logger.error("SOAP endpoint returned HTTP %s — treating as failure.", status_code)
        return False

    # A SOAP Fault element anywhere in the body is always a failure regardless of HTTP status.
    if "Fault" in response_body:
        logger.error("SOAP fault received:\n%s", response_body[:500])
        return False

    # Try to parse the body and look for an explicit Status element.
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
        logger.warning("Could not parse SOAP response as XML — response body:\n%s", response_body[:200])

    # HTTP 200/202 with no Fault and no Status element — treat as success.
    # Some endpoints return a minimal 200 OK with an empty or non-standard body.
    logger.info("HTTP %s received with no fault or status element — treating as success.", status_code)
    return True
