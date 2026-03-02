#!/usr/bin/env python3
"""
One-time script to pass SendGrid's "Send your first email" verification.
Run once: pip install sendgrid && python sendgrid_verify.py
Uses SENDGRID_API_KEY from env, or pass as first argument.
Sends to the same address as EMAIL_FROM so you get the test email.
"""
import os
import sys

# Load .env if present (use dotenv if available for correct parsing)
_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env):
    try:
        from dotenv import load_dotenv
        load_dotenv(_env)
    except ImportError:
        with open(_env) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k and v:
                        os.environ.setdefault(k, v)

api_key = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SENDGRID_API_KEY") or os.environ.get("SMTP_PASSWORD")
from_addr = os.environ.get("EMAIL_FROM", "adam@thegrowtharchitect.co.uk")

if not api_key:
    print("Usage: python sendgrid_verify.py YOUR_API_KEY")
    print("   or set SENDGRID_API_KEY or SMTP_PASSWORD in .env")
    sys.exit(1)

try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail
except ImportError:
    print("Run: pip install sendgrid")
    sys.exit(1)

message = Mail(
    from_email=from_addr,
    to_emails=from_addr,
    subject="SendGrid verification – Kinly",
    plain_text_content="If you got this, SendGrid is set up. You can use the same API key in .env as SMTP_PASSWORD.",
)
sg = SendGridAPIClient(api_key)
response = sg.send(message)
print(f"Sent. Status: {response.status_code}")
print("Check your inbox (and spam). Then use the same key in .env as SMTP_PASSWORD for the app.")
