"""App config from environment."""
import os

HUBSPOT_ACCESS_TOKEN = os.getenv("HUBSPOT_ACCESS_TOKEN", "")
HUBSPOT_STAFF_OBJECT_ID = os.getenv("HUBSPOT_STAFF_OBJECT_ID", "2-194632537")
HUBSPOT_LEAD_TEAM_OBJECT_ID = os.getenv("HUBSPOT_LEAD_TEAM_OBJECT_ID", "").strip() or None
# Optional: Staff custom object property for holidays (e.g. "holidays" or "blocked_dates"). Use a multi-line or rich text field. When set, holidays are stored per staff in HubSpot instead of the local JSON file.
HUBSPOT_STAFF_HOLIDAYS_PROPERTY = os.getenv("HUBSPOT_STAFF_HOLIDAYS_PROPERTY", "").strip() or None
HUBSPOT_LEAD_PIPELINE_STAGE = os.getenv("HUBSPOT_LEAD_PIPELINE_STAGE", "new-stage-id")

# Optional: if set, webhook requests must include this in X-Webhook-Secret header or ?secret= query
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip() or None

# Login: when SESSION_SECRET is set and at least one auth method is configured, dashboard requires login
SESSION_SECRET = os.getenv("SESSION_SECRET", "").strip() or None
# Password login: bcrypt hash (generate with: python -c "import bcrypt; print(bcrypt.hashpw(b'yourpassword', bcrypt.gensalt()).decode())")
APP_PASSWORD_HASH = os.getenv("APP_PASSWORD_HASH", "").strip() or None

# Passwordless login: one-time code to email. Set SMTP_* and EMAIL_FROM to enable.
SMTP_HOST = os.getenv("SMTP_HOST", "").strip() or None
try:
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587").strip() or "587")
except (ValueError, AttributeError):
    SMTP_PORT = 587
SMTP_USER = os.getenv("SMTP_USER", "").strip() or None
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip() or None
EMAIL_FROM = os.getenv("EMAIL_FROM", "").strip() or None
# Optional: comma-separated list; if set, only these addresses can request a code
ALLOWED_EMAILS_STR = os.getenv("ALLOWED_EMAILS", "").strip() or None
ALLOWED_EMAILS = [e.strip().lower() for e in (ALLOWED_EMAILS_STR or "").split(",") if e.strip()] or None

# Lead type to lead_priority mapping (contacts)
LEAD_PRIORITY_BY_TYPE = {
    "Inbound Lead Team": ["High", "High (Applied Before)", "High (Callback)"],
    "PIP Lead Team": ["PIP"],
    "Panther Lead Team": ["Panther"],
    "Frosties Lead Team": ["Frosties"],
}

# hs_lead_type values in Leads object
HS_LEAD_TYPES = {
    "inbound": "Inbound Lead",
    "pip": "PIP Lead",
    "frosties": "Frosties lead",
    "panther": "Panther Lead",
}

# Staff lead_teams (multi-select) options; used to match staff to lead type for re-assign
STAFF_LEAD_TEAMS = [
    "Frosties Lead Team",
    "Inbound Lead Team",
    "Panther Lead Team",
    "PIP Lead Team",
]

# Re-assign: map Staff team name -> hs_lead_type value for filtering leads
HS_LEAD_TYPE_BY_TEAM = {
    "Inbound Lead Team": "Inbound Lead",
    "PIP Lead Team": "PIP Lead",
    "Panther Lead Team": "Panther Lead",
    "Frosties Lead Team": "Frosties lead",
}

# Re-assign: pipeline stages to search (leads stay in their current stage; we only search within these)
REASSIGN_PIPELINE_STAGES = ["new-stage-id", "attempting-stage-id", "connected-stage-id"]

# Re-assign: Lead property for callback; if future date, lead counts only in Call Back category
REASSIGN_CALL_BACK_DATE_PROPERTY = "call_back_date"

# Re-assign: hs_tag_ids values for Attempt 1, 2, 3 (Lead object)
REASSIGN_TAG_ATTEMPT_1 = "37295391"
REASSIGN_TAG_ATTEMPT_2 = "37295488"
REASSIGN_TAG_ATTEMPT_3 = "37295491"
