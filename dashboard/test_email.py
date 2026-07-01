"""
Quick ACS email test — sends a test email using Azure Communication Services.
Run from the dashboard/ directory:

    uv run python test_email.py

Delete this file after use.
"""

from __future__ import annotations

import os
import sys


def _load_env_file() -> None:
    """Load dashboard/.env into the process environment if present."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return

    with open(env_path, encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


def main() -> int:
    """Send a one-off ACS test email from local dashboard configuration."""
    _load_env_file()

    acs_connection_string = os.getenv("ACS_CONNECTION_STRING", "")
    alert_email_to = os.getenv("ALERT_EMAIL_TO", "")
    alert_email_from = os.getenv("ALERT_EMAIL_FROM", "")

    missing = [
        key
        for key, value in {
            "ACS_CONNECTION_STRING": acs_connection_string,
            "ALERT_EMAIL_TO": alert_email_to,
            "ALERT_EMAIL_FROM": alert_email_from,
        }.items()
        if not value or value == "change-me"
    ]

    if missing:
        print(f"ERROR: missing or placeholder values in .env: {', '.join(missing)}")
        return 1

    from azure.communication.email import EmailClient  # noqa: PLC0415

    subject = "[Integration Hub] ACS test email"
    body = """\
<html><body style="font-family:Arial,sans-serif;color:#333;max-width:600px;">
<h2 style="color:#325083;border-bottom:2px solid #325083;padding-bottom:8px;">
  NHS Wales Integration Hub — ACS Email Test
</h2>
<p>This is a test email sent via Azure Communication Services.</p>
<p>If you received this, email notifications are working correctly.</p>
<p style="font-size:12px;color:#999;margin-top:24px;">
  Sent by test_email.py — delete this file after confirming.
</p>
</body></html>"""

    message = {
        "senderAddress": alert_email_from,
        "recipients": {"to": [{"address": alert_email_to}]},
        "content": {"subject": subject, "html": body},
    }

    print(f"Sending via ACS to {alert_email_to} ...")
    try:
        client = EmailClient.from_connection_string(acs_connection_string)
        poller = client.begin_send(message)
        result = poller.result()
        print(f"SUCCESS — message ID: {result.get('id', 'n/a')}")
        return 0
    except Exception as exc:
        print(f"FAILED — {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
