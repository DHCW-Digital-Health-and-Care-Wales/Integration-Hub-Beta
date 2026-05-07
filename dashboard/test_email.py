"""
Quick ACS email test — sends a test email using Azure Communication Services.
Run from the dashboard/ directory:

    uv run python test_email.py

Delete this file after use.
"""
import os
import sys

# ── Read .env manually ─────────────────────────────────────────────────────
_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as f:
        for raw_line in f:
            line = raw_line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

ACS_CONNECTION_STRING = os.getenv("ACS_CONNECTION_STRING", "")
ALERT_EMAIL_TO        = os.getenv("ALERT_EMAIL_TO", "")
ALERT_EMAIL_FROM      = os.getenv("ALERT_EMAIL_FROM", "")

# ── Validate ───────────────────────────────────────────────────────────────
missing = [k for k, v in {
    "ACS_CONNECTION_STRING": ACS_CONNECTION_STRING,
    "ALERT_EMAIL_TO":        ALERT_EMAIL_TO,
    "ALERT_EMAIL_FROM":      ALERT_EMAIL_FROM,
}.items() if not v or v == "change-me"]

if missing:
    print(f"ERROR: missing or placeholder values in .env: {', '.join(missing)}")
    sys.exit(1)

# ── Send ───────────────────────────────────────────────────────────────────
from azure.communication.email import EmailClient  # noqa: E402

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
    "senderAddress": ALERT_EMAIL_FROM,
    "recipients": {"to": [{"address": ALERT_EMAIL_TO}]},
    "content": {"subject": subject, "html": body},
}

print(f"Sending via ACS to {ALERT_EMAIL_TO} ...")
try:
    client = EmailClient.from_connection_string(ACS_CONNECTION_STRING)
    poller = client.begin_send(message)
    result = poller.result()
    print(f"SUCCESS — message ID: {result.get('id', 'n/a')}")
except Exception as exc:
    print(f"FAILED — {type(exc).__name__}: {exc}")
    sys.exit(1)

