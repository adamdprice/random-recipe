"""Configuration from environment."""
import os
from dotenv import load_dotenv

load_dotenv()

# HubSpot
HUBSPOT_ACCESS_TOKEN = os.getenv("HUBSPOT_ACCESS_TOKEN", "").strip()
HUBSPOT_STAFF_OBJECT_ID = os.getenv("HUBSPOT_STAFF_OBJECT_ID", "").strip()
HUBSPOT_LEAD_TEAM_OBJECT_ID = os.getenv("HUBSPOT_LEAD_TEAM_OBJECT_ID", "").strip()
HUBSPOT_LEAD_PIPELINE_STAGE = os.getenv("HUBSPOT_LEAD_PIPELINE_STAGE", "new-stage-id")

# Session / auth
SESSION_SECRET = os.getenv("SESSION_SECRET", "").strip()
if not SESSION_SECRET:
    SESSION_SECRET = os.urandom(32).hex()

# Email (SendGrid: SMTP_USER is "apikey", SMTP_PASSWORD is API key)
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.sendgrid.net")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
EMAIL_FROM = os.getenv("EMAIL_FROM", "").strip()
ALLOWED_EMAILS = [
    e.strip().lower()
    for e in os.getenv("ALLOWED_EMAILS", "").split(",")
    if e.strip()
]

# Data paths (file-based stores when no DB)
DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
HOLIDAYS_FILE = os.path.join(DATA_DIR, "holidays.json")
ACTIVITY_LOG_FILE = os.path.join(DATA_DIR, "activity_log.json")
