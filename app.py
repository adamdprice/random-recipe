"""
Kinly Lead Distribution - Flask API and dashboard.
"""
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

# Load .env from the app directory (works with or without python-dotenv)
_app_dir = os.path.dirname(os.path.abspath(__file__))
_env_path = os.path.join(_app_dir, ".env")
if os.path.exists(_env_path):
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_path)
    except ImportError:
        # Fallback: read .env and set os.environ
        with open(_env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    key, val = key.strip(), val.strip()
                    if key and val and val not in ('""', "''"):
                        os.environ.setdefault(key, val.strip('"').strip("'"))

from flask import Flask, request, jsonify, send_from_directory, redirect, make_response
from flask_cors import CORS

from config import (
    HUBSPOT_ACCESS_TOKEN,
    HUBSPOT_LEAD_TEAM_OBJECT_ID,
    HUBSPOT_STAFF_OBJECT_ID,
    HUBSPOT_STAFF_HOLIDAYS_PROPERTY,
    WEBHOOK_SECRET,
    SESSION_SECRET,
    APP_PASSWORD_HASH,
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASSWORD,
    EMAIL_FROM,
    ALLOWED_EMAILS,
    ENABLE_BACKGROUND_DISTRIBUTION,
)
from hubspot_client import HubSpotClient
from itsdangerous import URLSafeTimedSerializer
import bcrypt

# Map Lead Team name (from HubSpot) -> Staff object property to update when max_leads changes
TEAM_NAME_TO_STAFF_MAX_PROP = {
    "Inbound Lead Team": "max_inbound_leads",
    "PIP Lead Team": "max_pip_leads",
    "Panther Lead Team": "max_panther_leads",
    "Frosties Lead Team": "max_frosties_leads",
}

# Use absolute path so dashboard loads regardless of working directory
_frontend_dir = os.path.join(_app_dir, "frontend")
app = Flask(__name__, static_folder=_frontend_dir, static_url_path="")
CORS(app)

# Fallback body for any API 500 so frontend never sees HTML (defined early for after_request)
_API_500_JSON_BODY = json.dumps({
    "error": "An unexpected error occurred. Please try again. Check Railway logs for details.",
    "staff": [],
    "holidays": [],
    "owners": [],
    "lead_teams": [],
})


@app.after_request
def _api_500_ensure_json(response):
    """For any API 500, force JSON body so frontend never sees HTML (e.g. from Flask or proxy)."""
    path = ""
    try:
        if request:
            path = getattr(request, "path", "") or ""
    except Exception:
        pass
    if response.status_code == 500 and path.startswith("/api/"):
        # Replace with JSON if currently HTML or missing JSON content-type
        ct = (response.content_type or "").lower()
        is_json = "application/json" in ct
        try:
            data = response.get_data(as_text=True) if getattr(response, "get_data", None) else ""
            looks_html = data.strip().startswith("<") if isinstance(data, str) else False
        except Exception:
            looks_html = True
        if not is_json or looks_html:
            try:
                response.set_data(_API_500_JSON_BODY)
                response.content_type = "application/json"
            except Exception:
                pass
    return response


@app.route("/api/ping")
@app.route("/ping")
def _ping():
    """Instant response to verify server is responsive (no DB or HubSpot)."""
    return jsonify({"ping": "pong", "app": "kinly-lead-distribution"})


# Auth: when SESSION_SECRET is set and at least one method (password or email OTP) is configured
SESSION_COOKIE_NAME = "kinly_session"
SESSION_MAX_AGE_SECONDS = 24 * 3600  # 24 hours
EMAIL_OTP_ENABLED = bool(SESSION_SECRET and SMTP_HOST and EMAIL_FROM)
AUTH_ENABLED = bool(SESSION_SECRET and (APP_PASSWORD_HASH or EMAIL_OTP_ENABLED))

# One-time code store (in-memory): email -> { "code": str, "expires_at": timestamp }
_otp_store = {}
_otp_lock = threading.Lock()
# Rate limit: email -> last send time; IP -> list of send times (for cleanup we trim old)
_otp_email_last_send = {}
_otp_ip_sends = {}
OTP_CODE_EXPIRY_SECONDS = 15 * 60  # 15 minutes
OTP_RATE_EMAIL_SECONDS = 2 * 60  # 1 code per email per 2 minutes
OTP_RATE_IP_MAX = 10
OTP_RATE_IP_WINDOW = 15 * 60  # 10 sends per IP per 15 minutes

# HubSpot read cache (staff, lead_teams, owners) in PostgreSQL when DATABASE_URL is set
from hubspot_cache_db import (
    init_db as _init_hubspot_cache_db,
    cache_get as _hubspot_cache_get,
    cache_set as _hubspot_cache_set,
    cache_invalidate as _hubspot_cache_invalidate,
)
from holidays_db import init_holidays_db, holidays_load_all, holidays_save_all
from holidays import set_storage as _holidays_set_storage

_init_hubspot_cache_db()
init_holidays_db()
_redistribute_cache_available = False
_redistribute_get_counts_from_cache = None
_redistribute_get_lead_rows_from_cache = None
_redistribute_cache_has_data = lambda: False
_refresh_redistribute_cache_fn = None
_redistribute_remove_lead_ids_from_cache = None
try:
    from redistribute_cache_db import (
        init_redistribute_cache_db,
        refresh_redistribute_cache as _refresh_redistribute_cache_fn,
        get_counts_from_cache as _redistribute_get_counts_from_cache,
        get_lead_rows_from_cache as _redistribute_get_lead_rows_from_cache,
        cache_has_data as _redistribute_cache_has_data,
        remove_lead_ids_from_cache as _redistribute_remove_lead_ids_from_cache,
    )
    init_redistribute_cache_db()
    _redistribute_cache_available = True
except Exception as _e:  # noqa: F841
    import logging
    logging.getLogger(__name__).warning("Redistribute cache disabled: %s", _e)


def _hubspot_holidays_load() -> dict:
    """Load holidays from HubSpot Staff property (one JSON array per staff). Returns same shape as file: {holidays: [...], saved_availability: {}}."""
    if not HUBSPOT_STAFF_HOLIDAYS_PROPERTY or not HUBSPOT_STAFF_OBJECT_ID:
        return {"holidays": [], "saved_availability": {}}
    try:
        client = get_client()
        result = client.search_custom_objects(
            HUBSPOT_STAFF_OBJECT_ID,
            filter_groups=[{"filters": [{"propertyName": "hubspot_owner_id", "operator": "HAS_PROPERTY"}]}],
            properties=[HUBSPOT_STAFF_HOLIDAYS_PROPERTY],
            limit=100,
        )
        holidays = []
        for r in (result.get("results") or []):
            staff_id = str(r.get("id") or "")
            props = r.get("properties") or {}
            raw = props.get(HUBSPOT_STAFF_HOLIDAYS_PROPERTY)
            if isinstance(raw, dict) and "value" in raw:
                raw = raw["value"]
            if not raw or not isinstance(raw, str):
                continue
            try:
                arr = json.loads(raw)
            except (TypeError, ValueError):
                continue
            if not isinstance(arr, list):
                continue
            for h in arr:
                if isinstance(h, dict):
                    holidays.append({**h, "staff_id": staff_id})
        return {"holidays": holidays, "saved_availability": {}}
    except Exception as e:
        _log.warning("HubSpot holidays load failed: %s", e)
        return {"holidays": [], "saved_availability": {}}


def _hubspot_holidays_save(data: dict) -> None:
    """Save holidays back to HubSpot: group by staff_id, PATCH each staff's property."""
    if not HUBSPOT_STAFF_HOLIDAYS_PROPERTY or not HUBSPOT_STAFF_OBJECT_ID:
        return
    holidays = data.get("holidays") or []
    by_staff = {}
    for h in holidays:
        sid = str(h.get("staff_id") or "")
        if sid not in by_staff:
            by_staff[sid] = []
        by_staff[sid].append({k: v for k, v in h.items() if k != "staff_id"})
    try:
        client = get_client()
        # Staff that have the property set but now have no holidays: we must clear it
        result = client.search_custom_objects(
            HUBSPOT_STAFF_OBJECT_ID,
            filter_groups=[{"filters": [{"propertyName": HUBSPOT_STAFF_HOLIDAYS_PROPERTY, "operator": "HAS_PROPERTY"}]}],
            properties=["id"],
            limit=100,
        )
        for r in (result.get("results") or []):
            sid = str(r.get("id") or "")
            if sid not in by_staff:
                by_staff[sid] = []
        for staff_id, list_for_staff in by_staff.items():
            client.patch_custom_object(
                HUBSPOT_STAFF_OBJECT_ID,
                staff_id,
                {HUBSPOT_STAFF_HOLIDAYS_PROPERTY: json.dumps(list_for_staff)},
            )
    except Exception as e:
        _log.warning("HubSpot holidays save failed: %s", e)


def _holidays_db_load() -> dict:
    """
    Load holidays from PostgreSQL.
    If DB is empty but HUBSPOT_STAFF_HOLIDAYS_PROPERTY is set, seed from HubSpot once.
    """
    data = holidays_load_all()
    if (not data.get("holidays")) and HUBSPOT_STAFF_HOLIDAYS_PROPERTY:
        seed = _hubspot_holidays_load()
        if seed.get("holidays"):
            holidays_save_all(seed)
            return seed
    return data


def _holidays_db_save(data: dict) -> None:
    """Write holidays to PostgreSQL and (optionally) mirror to HubSpot property."""
    holidays_save_all(data)
    if HUBSPOT_STAFF_HOLIDAYS_PROPERTY:
        _hubspot_holidays_save(data)


if os.getenv("DATABASE_URL"):
    # Use PostgreSQL as canonical holidays store, optionally mirrored to HubSpot
    _holidays_set_storage(_holidays_db_load, _holidays_db_save)
elif HUBSPOT_STAFF_HOLIDAYS_PROPERTY:
    # No DB; fall back to storing holidays directly on Staff records in HubSpot
    _holidays_set_storage(_hubspot_holidays_load, _hubspot_holidays_save)


def _session_serializer():
    if not SESSION_SECRET:
        return None
    return URLSafeTimedSerializer(SESSION_SECRET, salt="kinly-login")


def _verify_session_cookie():
    if not AUTH_ENABLED:
        return True
    val = request.cookies.get(SESSION_COOKIE_NAME)
    if not val:
        return False
    ser = _session_serializer()
    if not ser:
        return False
    try:
        ser.loads(val, max_age=SESSION_MAX_AGE_SECONDS)
        return True
    except Exception:
        return False


def _set_session_cookie(response):
    ser = _session_serializer()
    if not ser:
        return response
    token = ser.dumps("authenticated")
    secure = os.getenv("FLASK_DEBUG", "").lower() not in ("1", "true", "yes")
    response.set_cookie(
        SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=secure,
        samesite="Lax",
        path="/",
    )
    return response


@app.before_request
def _require_auth():
    if not AUTH_ENABLED:
        return None
    path = request.path.rstrip("/") or "/"
    if path == "/login":
        return None
    if path == "/api/login" or path == "/api/logout":
        return None
    if path in ("/api/auth/send-code", "/api/auth/verify-code", "/api/auth/methods"):
        return None
    if path == "/api/health" or path == "/api/ping":
        return None
    if path == "/api/webhooks/lead-team-max-leads":
        return None
    if _verify_session_cookie():
        return None
    # Unauthenticated: redirect main page to login
    if path == "/":
        return redirect("/login")
    # Allow static assets (login page needs logo, CSS, etc.) without auth
    if not path.startswith("/api/"):
        return None
    return jsonify({"error": "Unauthorized"}), 401


# Background refresh every 6 minutes: staff open leads + team max_leads → staff
REFRESH_INTERVAL_SECONDS = 6 * 60  # 6 minutes
_log = logging.getLogger(__name__)

# In-memory activity log (last N events) for dashboard visibility
_activity_log: list = []
_activity_log_max = 100
_activity_lock = threading.Lock()

# Manual refresh: run in background so the HTTP request doesn't time out
_refresh_in_progress = False
_refresh_lock = threading.Lock()

# After create_staff(), any list_staff() that writes to cache must include the new staff for 2 min.
# Stored in DB (staff_created_cooldown) so all workers see it.
STAFF_CREATED_COOLDOWN_SECONDS = 120


def _log_activity(event: str, message: str, details: Optional[dict] = None) -> None:
    """Append an entry to the activity log (thread-safe)."""
    from datetime import datetime, timezone
    entry = {
        "time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "event": event,
        "message": message,
    }
    if details:
        entry["details"] = details
    with _activity_lock:
        _activity_log.append(entry)
        while len(_activity_log) > _activity_log_max:
            _activity_log.pop(0)


def get_client() -> HubSpotClient:
    if not HUBSPOT_ACCESS_TOKEN:
        raise ValueError("HUBSPOT_ACCESS_TOKEN not set")
    return HubSpotClient(HUBSPOT_ACCESS_TOKEN)


# Call minutes in last 120 minutes (for temperature gauge)
CALL_MINUTES_WINDOW = 120
# Fetch calls that started this far back so we include long calls that overlap the window
CALL_FETCH_WINDOW_MINUTES = 360  # 6 hours


def _timestamp_to_ms(ts: Any) -> Optional[int]:
    """Convert HubSpot timestamp (ISO 8601 string or epoch number in sec/ms) to epoch milliseconds."""
    if ts is None:
        return None
    if isinstance(ts, dict) and "value" in ts:
        ts = ts["value"]
    if isinstance(ts, str):
        ts = ts.strip()
        if not ts:
            return None
        # ISO 8601 e.g. "2024-01-17T19:55:04.281Z"
        if "T" in ts or "-" in ts:
            try:
                # fromisoformat needs Z replaced for Python 3.10 and earlier
                normalized = ts.replace("Z", "+00:00")
                dt = datetime.fromisoformat(normalized)
                return int(dt.timestamp() * 1000)
            except Exception:
                return None
        try:
            n = int(ts)
            return n * 1000 if n < 1e12 else n
        except (TypeError, ValueError):
            return None
    try:
        n = int(ts)
        return n * 1000 if n < 1e12 else n
    except (TypeError, ValueError):
        return None


def _duration_to_ms(dur: Any) -> Optional[int]:
    """Convert HubSpot call duration to milliseconds (API reports duration in ms)."""
    if dur is None:
        return None
    if isinstance(dur, dict) and "value" in dur:
        dur = dur["value"]
    try:
        return int(dur)
    except (TypeError, ValueError):
        return None


def _get_call_minutes_last_120(client: HubSpotClient, hubspot_owner_id: str):
    """Sum call duration for this owner in the last 120 minutes. Only counts the portion of each
    call that falls inside the 2-hour window (calls that span the window boundary are prorated).
    Returns minutes, or None on error."""
    if not hubspot_owner_id:
        return 0
    try:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        window_ms = CALL_MINUTES_WINDOW * 60 * 1000
        since_ms = now_ms - window_ms
        fetch_since_ms = now_ms - (CALL_FETCH_WINDOW_MINUTES * 60 * 1000)
        res = client.search_calls(
            filter_groups=[{
                "filters": [
                    {"propertyName": "hubspot_owner_id", "operator": "EQ", "value": str(hubspot_owner_id)},
                    {"propertyName": "hs_timestamp", "operator": "GTE", "value": str(fetch_since_ms)},
                ],
            }],
            properties=["hs_timestamp", "hs_call_duration"],
            limit=100,
        )
        total_ms = 0
        for r in res.get("results", []):
            props = r.get("properties") or {}
            start_ms = _timestamp_to_ms(props.get("hs_timestamp"))
            duration_ms = _duration_to_ms(props.get("hs_call_duration"))
            if start_ms is None or duration_ms is None:
                continue
            end_ms = start_ms + duration_ms
            # Overlap of call [start_ms, end_ms] with window [since_ms, now_ms]
            overlap_start = max(start_ms, since_ms)
            overlap_end = min(end_ms, now_ms)
            overlap_ms = max(0, overlap_end - overlap_start)
            total_ms += overlap_ms
        return round(total_ms / 60000)  # milliseconds to minutes
    except Exception:
        return None


# --- Health ---
@app.route("/api/health")
def health():
    return jsonify({"ok": True, "hubspot_configured": bool(HUBSPOT_ACCESS_TOKEN)})




# --- Login (when SESSION_SECRET and APP_PASSWORD_HASH are set) ---
@app.route("/login", methods=["GET"])
def login_page():
    folder = app.static_folder or ""
    login_path = os.path.join(folder, "login.html")
    if folder and os.path.isfile(login_path):
        return send_from_directory(folder, "login.html")
    return "<p>Login page not found.</p>", 404


@app.route("/api/login", methods=["POST"])
def login():
    if not AUTH_ENABLED:
        return jsonify({"ok": True})
    data = request.get_json(silent=True) or {}
    password = (data.get("password") or "").encode("utf-8")
    if not password:
        return jsonify({"error": "Password required"}), 400
    stored_hash = (APP_PASSWORD_HASH or "").encode("utf-8")
    if not stored_hash:
        return jsonify({"error": "Password required"}), 400
    try:
        if not bcrypt.checkpw(password, stored_hash):
            return jsonify({"error": "Invalid password"}), 401
    except Exception:
        return jsonify({"error": "Invalid password"}), 401
    resp = jsonify({"ok": True})
    return _set_session_cookie(resp)


@app.route("/api/logout", methods=["POST"])
def logout():
    resp = jsonify({"ok": True})
    resp.set_cookie(
        SESSION_COOKIE_NAME,
        value="",
        max_age=0,
        httponly=True,
        secure=os.getenv("FLASK_DEBUG", "").lower() not in ("1", "true", "yes"),
        samesite="Lax",
        path="/",
    )
    return resp


# --- Passwordless: one-time code to email ---
def _send_otp_email(to_email: str, code: str) -> None:
    """Send OTP code. Prefer SendGrid API when using SendGrid (same as verification); else SMTP."""
    subject = f"Kinly Lead Distribution verification code (expires in 15 minutes) {datetime.now(timezone.utc).strftime('%d%m%y - %H:%M')}"
    body = f"""Hi there,

Here's your one-time sign-in code for the Kinly Lead Distribution App:

{code}

This code will expire in 15 minutes.

If you didn't request this sign-in code, you can safely ignore this email.

Thanks,
Kinly Lead Distribution App"""
    # Use SendGrid HTTP API when we have their key (same method that passed verification)
    if SMTP_HOST and "sendgrid" in SMTP_HOST.lower() and SMTP_PASSWORD:
        try:
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import Mail
            message = Mail(
                from_email=EMAIL_FROM,
                to_emails=to_email,
                subject=subject,
                plain_text_content=body,
            )
            sg = SendGridAPIClient(SMTP_PASSWORD)
            response = sg.send(message)
            if response.status_code not in (200, 201, 202):
                raise RuntimeError(f"SendGrid returned {response.status_code}")
            return
        except Exception as e:
            _log.warning("SendGrid API send failed (%s), trying SMTP", e)
    # SMTP fallback
    import ssl
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = to_email
    msg.attach(MIMEText(body, "plain"))
    context = ssl.create_default_context()
    if SMTP_PORT == 465:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=30) as smtp:
            if SMTP_USER and SMTP_PASSWORD:
                smtp.login(SMTP_USER, SMTP_PASSWORD)
            smtp.sendmail(EMAIL_FROM, [to_email], msg.as_string())
    else:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
            smtp.starttls(context=context)
            if SMTP_USER and SMTP_PASSWORD:
                smtp.login(SMTP_USER, SMTP_PASSWORD)
            smtp.sendmail(EMAIL_FROM, [to_email], msg.as_string())


@app.route("/api/auth/methods", methods=["GET"])
def auth_methods():
    """Return which login methods are enabled (for login page UI)."""
    return jsonify({
        "password": bool(APP_PASSWORD_HASH),
        "email_code": EMAIL_OTP_ENABLED,
    })


@app.route("/api/auth/send-code", methods=["POST"])
def send_code():
    """Send a one-time code to the given email. Rate-limited."""
    if not EMAIL_OTP_ENABLED:
        return jsonify({"error": "Email sign-in is not configured"}), 400
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return jsonify({"error": "Valid email required"}), 400
    if ALLOWED_EMAILS and email not in ALLOWED_EMAILS:
        return jsonify({"error": "This email is not allowed to sign in"}), 403
    now = time.time()
    with _otp_lock:
        # Rate limit per email
        last = _otp_email_last_send.get(email, 0)
        if now - last < OTP_RATE_EMAIL_SECONDS:
            return jsonify({"error": "Please wait a few minutes before requesting another code"}), 429
        # Rate limit per IP
        ip = request.remote_addr or "unknown"
        window_start = now - OTP_RATE_IP_WINDOW
        _otp_ip_sends.setdefault(ip, [])
        _otp_ip_sends[ip] = [t for t in _otp_ip_sends[ip] if t > window_start]
        if len(_otp_ip_sends[ip]) >= OTP_RATE_IP_MAX:
            return jsonify({"error": "Too many requests; try again later"}), 429
        _otp_ip_sends[ip].append(now)
        # Generate and store code
        import random
        code = "".join(str(random.randint(0, 9)) for _ in range(6))
        _otp_store[email] = {"code": code, "expires_at": now + OTP_CODE_EXPIRY_SECONDS}
        _otp_email_last_send[email] = now
    try:
        _send_otp_email(email, code)
    except Exception as e:
        _log.exception("Send OTP email failed: %s", e)
        with _otp_lock:
            _otp_store.pop(email, None)
        return jsonify({"error": "Failed to send email; try again later"}), 500
    return jsonify({"ok": True, "message": "Check your email for the code"})


@app.route("/api/auth/verify-code", methods=["POST"])
def verify_code():
    """Verify one-time code and set session cookie."""
    if not EMAIL_OTP_ENABLED:
        return jsonify({"error": "Email sign-in is not configured"}), 400
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    code = (data.get("code") or "").strip()
    if not email or not code:
        return jsonify({"error": "Email and code required"}), 400
    now = time.time()
    with _otp_lock:
        entry = _otp_store.get(email)
        if not entry:
            return jsonify({"error": "Invalid or expired code"}), 401
        if now > entry["expires_at"]:
            del _otp_store[email]
            return jsonify({"error": "Code has expired; request a new one"}), 401
        if entry["code"] != code:
            return jsonify({"error": "Invalid code"}), 401
        del _otp_store[email]
    resp = jsonify({"ok": True})
    return _set_session_cookie(resp)


# --- Lead Teams (list + patch max_leads) ---
def _count_unallocated_contacts(client: HubSpotClient, lead_priority_values: list[str]) -> int:
    """Count contacts with no owner, no assign_lead, lead_priority in values, and hs_lead_status = Open Lead."""
    if not lead_priority_values:
        return 0
    search_res = client.search_contacts(
        filter_groups=[{
            "filters": [
                {"propertyName": "hubspot_owner_id", "operator": "NOT_HAS_PROPERTY"},
                {"propertyName": "assign_lead", "operator": "NOT_HAS_PROPERTY"},
                {"propertyName": "lead_priority", "operator": "IN", "values": lead_priority_values},
                {"propertyName": "hs_lead_status", "operator": "EQ", "value": "Open Lead"},
            ],
        }],
        properties=["lead_priority"],
        limit=1,
    )
    return search_res.get("total", 0) or 0


@app.route("/api/lead-teams", methods=["GET"])
def list_lead_teams():
    try:
        if not HUBSPOT_LEAD_TEAM_OBJECT_ID:
            return jsonify({"lead_teams": [], "message": "HUBSPOT_LEAD_TEAM_OBJECT_ID not set"}), 200
        if request.args.get("refresh") != "1":
            cached = _hubspot_cache_get("lead_teams")
            if cached is not None:
                return jsonify(cached)
        client = get_client()
        out = _fetch_lead_teams_from_hubspot(client)
        _hubspot_cache_set("lead_teams", out)
        return jsonify(out)
    except Exception as e:
        _log.exception("list_lead_teams failed")
        return _safe_json_response({"error": str(e) if e else "Unknown error", "lead_teams": []}, 500)


def _prop_value(props: dict, key: str):
    """Get a HubSpot property value (handles { value: ... } wrapper)."""
    v = props.get(key) if isinstance(props, dict) else None
    if v is None:
        return None
    if isinstance(v, dict) and "value" in v:
        return v["value"]
    return v


def propagate_team_max_leads_to_staff(client: HubSpotClient, team_object_id: str, new_max_leads: int) -> int:
    """
    Update all staff in the given lead team with the new max_leads on the matching max_* property.
    Returns the number of staff records updated.
    """
    if not HUBSPOT_STAFF_OBJECT_ID or not HUBSPOT_LEAD_TEAM_OBJECT_ID:
        return 0
    team_record = client.get_custom_object(
        HUBSPOT_LEAD_TEAM_OBJECT_ID,
        team_object_id,
        properties=["name"],
    )
    props = team_record.get("properties") or {}
    team_name = _prop_value(props, "name")
    staff_prop = TEAM_NAME_TO_STAFF_MAX_PROP.get(team_name) if team_name else None
    if not staff_prop:
        return 0
    search_result = client.search_custom_objects(
        HUBSPOT_STAFF_OBJECT_ID,
        filter_groups=[{
            "filters": [{
                "propertyName": "lead_teams",
                "operator": "CONTAINS_TOKEN",
                "value": team_name,
            }],
        }],
        properties=["name"],
        limit=100,
    )
    results = search_result.get("results") or []
    if not results:
        return 0
    inputs = [
        {"id": str(r["id"]), "properties": {staff_prop: str(new_max_leads)}}
        for r in results
    ]
    client.batch_update_custom_objects(HUBSPOT_STAFF_OBJECT_ID, inputs)
    return len(inputs)


def _fetch_lead_teams_from_hubspot(client: HubSpotClient):
    """Fetch lead teams + unallocated counts from HubSpot. Returns dict for cache: {"lead_teams": [...]}."""
    from config import LEAD_PRIORITY_BY_TYPE
    if not HUBSPOT_LEAD_TEAM_OBJECT_ID:
        return {"lead_teams": []}
    result = client.search_custom_objects(
        HUBSPOT_LEAD_TEAM_OBJECT_ID,
        filter_groups=[{"filters": [{"propertyName": "name", "operator": "HAS_PROPERTY"}]}],
        properties=["name", "max_leads"],
        limit=100,
    )
    if not isinstance(result, dict):
        result = {"results": []}
    items = []
    for r in result.get("results", []):
        props = r.get("properties") or {}
        if not isinstance(props, dict):
            continue
        team_name = _prop_value(props, "name") or r.get("id")
        priorities = LEAD_PRIORITY_BY_TYPE.get(team_name, []) if team_name else []
        unallocated = _count_unallocated_contacts(client, priorities) if priorities else 0
        items.append({
            "id": r.get("id"),
            "name": team_name,
            "max_leads": _prop_value(props, "max_leads"),
            "unallocated": unallocated,
        })
    return {"lead_teams": items}


def _fetch_owners_from_hubspot(client: HubSpotClient):
    """Fetch HubSpot owners. Returns dict for cache: {"owners": [...]}."""
    owners = client.get_owners()
    out = []
    for o in owners if isinstance(owners, list) else []:
        out.append({
            "id": o.get("id"),
            "firstName": o.get("firstName") or "",
            "lastName": o.get("lastName") or "",
            "email": o.get("email") or "",
        })
    return {"owners": out}


def _fetch_staff_from_hubspot(client: HubSpotClient):
    """Fetch staff + call minutes from HubSpot. Returns dict for cache: {"staff": [...]}. Slow (N+1 call-minutes)."""
    from config import HUBSPOT_STAFF_OBJECT_ID
    result = client.search_custom_objects(
        HUBSPOT_STAFF_OBJECT_ID,
        filter_groups=[{"filters": [{"propertyName": "hubspot_owner_id", "operator": "HAS_PROPERTY"}]}],
        properties=[
            "name", "hubspot_owner_id", "lead_teams", "availability", "pause_leads",
            "max_pip_leads", "max_inbound_leads", "max_panther_leads", "max_frosties_leads",
            "open_pip_leads_n8n", "open_inbound_leads_n8n", "open_panther_leads", "open_frosties_leads",
        ],
        limit=100,
    )
    if not isinstance(result, dict):
        result = {"results": []}
    items = []
    for r in result.get("results", []):
        props = r.get("properties") or {}
        if not isinstance(props, dict):
            continue
        owner_id = _prop_value(props, "hubspot_owner_id")
        display_name = _prop_value(props, "name") or owner_id or "—"
        items.append({
            "id": r.get("id"),
            "hubspot_owner_id": owner_id,
            "name": display_name,
            "lead_teams": _prop_value(props, "lead_teams"),
            "availability": _prop_value(props, "availability"),
            "pause_leads": _prop_value(props, "pause_leads"),
            "max_pip_leads": _prop_value(props, "max_pip_leads"),
            "max_inbound_leads": _prop_value(props, "max_inbound_leads"),
            "max_panther_leads": _prop_value(props, "max_panther_leads"),
            "max_frosties_leads": _prop_value(props, "max_frosties_leads"),
            "open_pip_leads_n8n": _prop_value(props, "open_pip_leads_n8n"),
            "open_inbound_leads_n8n": _prop_value(props, "open_inbound_leads_n8n"),
            "open_panther_leads": _prop_value(props, "open_panther_leads"),
            "open_frosties_leads": _prop_value(props, "open_frosties_leads"),
        })
    from holidays import is_staff_on_holiday_today
    for item in items:
        item["on_holiday_today"] = is_staff_on_holiday_today(str(item["id"]))
    for i, item in enumerate(items):
        if i > 0:
            time.sleep(0.2)
        mins = _get_call_minutes_last_120(client, item.get("hubspot_owner_id"))
        item["call_minutes_last_120"] = mins if mins is not None else 0
    return {"staff": items}


def _warm_hubspot_cache() -> None:
    """Fetch staff, lead_teams, owners from HubSpot and write to DB cache. Safe to call from background thread."""
    if not HUBSPOT_ACCESS_TOKEN:
        return
    try:
        client = get_client()
        _hubspot_cache_set("lead_teams", _fetch_lead_teams_from_hubspot(client))
    except Exception as e:
        _log.warning("Cache warm lead_teams failed: %s", e)
    try:
        client = get_client()
        _hubspot_cache_set("owners", _fetch_owners_from_hubspot(client))
    except Exception as e:
        _log.warning("Cache warm owners failed: %s", e)
    try:
        client = get_client()
        _hubspot_cache_set("staff", _fetch_staff_from_hubspot(client))
    except Exception as e:
        _log.warning("Cache warm staff failed: %s", e)


def run_periodic_refresh() -> None:
    """
    Run the full refresh: (1) recalc staff open lead counts, (2) apply holiday availability,
    (3) sync each lead team's max_leads to staff, (4) run distribution and assign leads.
    Safe to call from a background thread.
    """
    if not HUBSPOT_ACCESS_TOKEN:
        return
    _log_activity("refresh_start", "Background refresh started", {"source": "scheduled"})
    try:
        client = get_client()
        # 1) Refresh open lead counts for all staff
        from distribution_engine import refresh_staff_open_leads
        result = refresh_staff_open_leads()
        updated = result.get("updated", 0)
        errors = result.get("errors", [])
        _log.info("Periodic refresh: staff open leads updated=%s", updated)
        _log_activity(
            "refresh_leads",
            f"Updated open lead counts for {updated} staff",
            {"updated": updated, "errors": len(errors)},
        )
        # 2) Apply holiday availability: set Unavailable for staff on holiday today, restore when back
        if HUBSPOT_STAFF_OBJECT_ID:
            from holidays import apply_holiday_availability
            staff_result = client.search_custom_objects(
                HUBSPOT_STAFF_OBJECT_ID,
                filter_groups=[{"filters": [{"propertyName": "hubspot_owner_id", "operator": "HAS_PROPERTY"}]}],
                properties=["availability"],
                limit=100,
            )
            staff_list = [{"id": r.get("id"), "availability": _prop_value(r.get("properties") or {}, "availability")} for r in (staff_result.get("results") or [])]
            holiday_updates = apply_holiday_availability(client, HUBSPOT_STAFF_OBJECT_ID, staff_list)
            changed = (holiday_updates.get("set_unavailable") or 0) + (holiday_updates.get("restored") or 0)
            if changed > 0:
                _log_activity(
                    "refresh_holidays",
                    "Holiday availability applied",
                    {"set_unavailable": holiday_updates.get("set_unavailable", 0), "restored": holiday_updates.get("restored", 0)},
                )
        # 3) For each lead team, propagate its current max_leads to staff in that team
        if HUBSPOT_LEAD_TEAM_OBJECT_ID and HUBSPOT_STAFF_OBJECT_ID:
            search_result = client.search_custom_objects(
                HUBSPOT_LEAD_TEAM_OBJECT_ID,
                filter_groups=[{"filters": [{"propertyName": "name", "operator": "HAS_PROPERTY"}]}],
                properties=["name", "max_leads"],
                limit=100,
            )
            for r in (search_result.get("results") or []):
                tid = r.get("id")
                props = r.get("properties") or {}
                max_leads = _prop_value(props, "max_leads")
                if tid is not None and max_leads is not None:
                    try:
                        n = int(max_leads)
                        propagate_team_max_leads_to_staff(client, str(tid), n)
                    except (TypeError, ValueError):
                        pass
        # 4) Run distribution for all active staff (same as test run but actually assign leads)
        from distribution_engine import run_distribution_for_all_active
        dist_result = run_distribution_for_all_active(dry_run=False)
        summary = dist_result.get("summary") or {}
        total_assignments = summary.get("total_assignments", 0)
        owners_processed = summary.get("owners_processed", 0)
        at_capacity_count = summary.get("at_capacity_count", 0)
        msg = f"Distribution completed: assigned {total_assignments} contact(s) across {owners_processed} staff"
        if total_assignments == 0 and at_capacity_count:
            msg += f" ({at_capacity_count} at capacity)"
        elif total_assignments == 0 and owners_processed:
            msg += " (none at capacity; possible no unallocated Open Lead contacts)"
        _log_activity(
            "distribution",
            msg,
            {"source": "scheduled", "total_assignments": total_assignments, "owners_processed": owners_processed, "at_capacity_count": at_capacity_count},
        )
        _log_activity("refresh_done", "Background refresh completed")
    except Exception as e:
        _log.exception("Periodic refresh failed: %s", e)
        _log_activity("refresh_error", f"Refresh failed: {e}", {"error": str(e)})


@app.route("/api/lead-teams/<object_id>", methods=["PATCH"])
def patch_lead_team(object_id):
    if not HUBSPOT_LEAD_TEAM_OBJECT_ID:
        return jsonify({"error": "HUBSPOT_LEAD_TEAM_OBJECT_ID not set"}), 400
    data = request.get_json() or {}
    max_leads = data.get("max_leads")
    if max_leads is None:
        return jsonify({"error": "max_leads required"}), 400
    try:
        client = get_client()
        new_value = int(max_leads)
        client.patch_custom_object(
            HUBSPOT_LEAD_TEAM_OBJECT_ID,
            object_id,
            {"max_leads": new_value},
        )
        propagate_team_max_leads_to_staff(client, object_id, new_value)
        _hubspot_cache_invalidate("lead_teams", "staff")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Webhook: HubSpot lead team max_leads changed (propagate to staff) ---
@app.route("/api/webhooks/lead-team-max-leads", methods=["POST"])
def webhook_lead_team_max_leads():
    """
    Called when a lead team's max_leads is updated (e.g. in HubSpot or by another system).
    Payload shape (from n8n / typical webhook): body[0] or top-level with objectId, propertyName, propertyValue.
    """
    if WEBHOOK_SECRET:
        secret = request.headers.get("X-Webhook-Secret") or request.args.get("secret")
        if secret != WEBHOOK_SECRET:
            return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    # Support body[0] (array) or flat object
    payload = data.get("body")
    if isinstance(payload, list) and payload:
        payload = payload[0]
    if not isinstance(payload, dict):
        payload = data
    object_id = payload.get("objectId") or payload.get("object_id")
    property_name = (payload.get("propertyName") or payload.get("property_name") or "").strip()
    property_value = payload.get("propertyValue") or payload.get("property_value")
    if property_name and property_name != "max_leads":
        return jsonify({"ok": True, "skipped": "not max_leads"}), 200
    if not object_id:
        return jsonify({"error": "objectId required"}), 400
    try:
        new_value = int(property_value) if property_value is not None else None
    except (TypeError, ValueError):
        return jsonify({"error": "invalid propertyValue"}), 400
    if new_value is None:
        return jsonify({"error": "propertyValue required"}), 400
    if not HUBSPOT_LEAD_TEAM_OBJECT_ID or not HUBSPOT_STAFF_OBJECT_ID:
        return jsonify({"ok": True, "skipped": "config missing"}), 200
    try:
        client = get_client()
        updated = propagate_team_max_leads_to_staff(client, str(object_id), new_value)
        _hubspot_cache_invalidate("lead_teams", "staff")
        return jsonify({"ok": True, "staff_updated": updated}), 200
    except Exception as e:
        app.logger.exception("Webhook lead-team-max-leads failed")
        return jsonify({"ok": False, "error": str(e)}), 500


# --- Staff (list + patch availability) ---
def _run_manual_refresh_background() -> None:
    """Run refresh in background; logs to activity when done. Avoids request timeout."""
    global _refresh_in_progress
    try:
        from distribution_engine import refresh_staff_open_leads
        result = refresh_staff_open_leads()
        updated = result.get("updated", 0)
        _hubspot_cache_invalidate("staff", "lead_teams")
        _log_activity("refresh_leads", f"Manual refresh: updated {updated} staff", {"source": "manual", "updated": updated})
    except Exception as e:
        _log_activity("refresh_error", f"Manual refresh failed: {e}", {"source": "manual", "error": str(e)})
    finally:
        with _refresh_lock:
            _refresh_in_progress = False


@app.route("/api/staff/refresh-leads", methods=["POST"])
def refresh_staff_leads():
    """Start refresh in background and return immediately (avoids Railway request timeout)."""
    global _refresh_in_progress
    with _refresh_lock:
        if _refresh_in_progress:
            return jsonify({"status": "already_running", "updated": 0}), 200
        _refresh_in_progress = True
    thread = threading.Thread(target=_run_manual_refresh_background, daemon=True, name="manual-refresh")
    thread.start()
    return jsonify({"status": "started", "updated": 0})


@app.route("/api/activity-log", methods=["GET"])
def activity_log():
    """Return recent activity log entries (refreshes, errors). Most recent last."""
    limit = min(int(request.args.get("limit", 50)), 200)
    with _activity_lock:
        entries = list(_activity_log[-limit:])
    return jsonify({"entries": entries})


# Max time to wait for /api/staff when fetching from HubSpot (cache miss). Keep below gunicorn --timeout 90 so worker is not killed.
STAFF_FETCH_TIMEOUT_SECONDS = 40


@app.route("/api/staff", methods=["GET"])
def list_staff():
    try:
        if request.args.get("refresh") != "1":
            cached = _hubspot_cache_get("staff")
            if cached is not None:
                # Even on cache hit, ensure just-created staff is in the list (e.g. 5-min refresh had stale cache)
                cd = _hubspot_cache_get("staff_created_cooldown")
                if cd and time.time() < cd.get("until", 0):
                    new_one = cd.get("staff")
                    staff_list = list(cached.get("staff") or [])
                    if new_one and not any(str(s.get("id")) == str(new_one.get("id")) for s in staff_list):
                        cached = {"staff": staff_list + [new_one]}
                return jsonify(cached)
        client = get_client()
        result_holder: list = []
        exc_holder: list = []

        def fetch():
            try:
                result_holder.append(_fetch_staff_from_hubspot(client))
            except Exception as e:
                exc_holder.append(e)

        thread = threading.Thread(target=fetch, daemon=True)
        thread.start()
        thread.join(timeout=STAFF_FETCH_TIMEOUT_SECONDS)
        if exc_holder:
            raise exc_holder[0]
        if not result_holder:
            return _safe_json_response({
                "error": "Staff list is taking too long to load. Try again in a moment or click Refresh.",
                "staff": [],
            }, 503)
        out = result_holder[0]
        # If we recently created a staff (stored in DB so all workers see it), ensure they're in the list
        cd = _hubspot_cache_get("staff_created_cooldown")
        if cd and time.time() < cd.get("until", 0):
            new_one = cd.get("staff")
            staff_list = out.get("staff") or []
            if new_one and not any(str(s.get("id")) == str(new_one.get("id")) for s in staff_list):
                out = {"staff": staff_list + [new_one]}
        _hubspot_cache_set("staff", out)
        return jsonify(out)
    except Exception as e:
        _log.exception("list_staff failed")
        return _safe_json_response({"error": str(e) if e else "Unknown error", "staff": []}, 500)


@app.route("/api/owners", methods=["GET"])
def list_owners():
    """Return HubSpot owners (for creating a new staff member)."""
    try:
        if request.args.get("refresh") != "1":
            cached = _hubspot_cache_get("owners")
            if cached is not None:
                return jsonify(cached)
        client = get_client()
        payload = _fetch_owners_from_hubspot(client)
        _hubspot_cache_set("owners", payload)
        return jsonify(payload)
    except Exception as e:
        _log.exception("list_owners failed")
        return _safe_json_response({"error": str(e) if e else "Unknown error", "owners": []}, 500)


@app.route("/api/staff", methods=["POST"])
def create_staff():
    """
    Create a new staff member in HubSpot. One staff per owner.
    Body: { "hubspot_owner_id": "<owner_id>", "lead_teams": ["Inbound Lead Team", ...] or "Inbound Lead Team;PIP Lead Team" }.
    Returns the created staff (same shape as list_staff items) so the UI can add without refresh.
    """
    from config import HUBSPOT_STAFF_OBJECT_ID
    data = request.get_json() or {}
    owner_id = (data.get("hubspot_owner_id") or "").strip()
    if not owner_id:
        return jsonify({"error": "hubspot_owner_id is required"}), 400
    lead_teams_raw = data.get("lead_teams")
    if isinstance(lead_teams_raw, list):
        # HubSpot multi-select expects semicolon-separated values (no space)
        lead_teams_str = ";".join(str(t).strip() for t in lead_teams_raw if t)
    elif isinstance(lead_teams_raw, str):
        lead_teams_str = lead_teams_raw.strip().replace("; ", ";")
    else:
        lead_teams_str = ""
    try:
        client = get_client()
        # Check if this owner already has a staff member
        existing = client.get_staff_by_owner_id(str(owner_id), HUBSPOT_STAFF_OBJECT_ID, properties=["hubspot_owner_id"])
        if (existing.get("results") or []):
            return jsonify({"error": "This user already has a staff member"}), 400
        # Resolve owner name (users who haven't accepted the HubSpot invite have no first/last name)
        owners = client.get_owners()
        first_name = ""
        last_name = ""
        owner_email = ""
        owner_found = False
        for o in (owners or []):
            if str(o.get("id")) == str(owner_id):
                first_name = (o.get("firstName") or "").strip()
                last_name = (o.get("lastName") or "").strip()
                owner_email = (o.get("email") or "").strip()
                owner_found = True
                break
        name = " ".join([first_name, last_name]).strip() or str(owner_id)
        no_name_msg = "This user has no name in HubSpot and cannot be added as staff. Add a name in HubSpot or choose another user."
        no_email_msg = "This user has no proper name in HubSpot (only an email). Add a first and last name in HubSpot or choose another user."
        if not owner_found:
            return jsonify({"error": no_name_msg}), 400
        if not first_name and not last_name:
            return jsonify({"error": no_name_msg}), 400
        if not name or name.strip() == str(owner_id):
            return jsonify({"error": no_name_msg}), 400
        if name.strip().isdigit() and name.strip() == str(owner_id).strip():
            return jsonify({"error": no_name_msg}), 400
        if "@" in name:
            return jsonify({"error": no_email_msg}), 400
        if owner_email and name.strip().lower() == owner_email.lower():
            return jsonify({"error": no_email_msg}), 400
        # Create Staff custom object: availability Unavailable, optional teams
        props = {
            "hubspot_owner_id": str(owner_id),
            "name": name,
            "availability": "Unavailable",
            "lead_teams": lead_teams_str,
            "max_inbound_leads": "0",
            "max_pip_leads": "0",
            "max_panther_leads": "0",
            "max_frosties_leads": "0",
            "open_inbound_leads_n8n": "0",
            "open_pip_leads_n8n": "0",
            "open_panther_leads": "0",
            "open_frosties_leads": "0",
        }
        created = client.create_custom_object(HUBSPOT_STAFF_OBJECT_ID, props)
        staff_id = created.get("id")
        if not staff_id:
            return jsonify({"error": "HubSpot did not return the new staff id"}), 500
        # Ensure lead_teams is set (create often doesn't persist multi-select; PATCH does)
        lead_teams_warning = None
        if lead_teams_str:
            try:
                client.patch_custom_object(
                    HUBSPOT_STAFF_OBJECT_ID,
                    str(staff_id),
                    {"lead_teams": lead_teams_str},
                )
            except Exception as patch_err:
                logging.exception("PATCH lead_teams after create failed")
                lead_teams_warning = str(patch_err)
        # Return same shape as list_staff item so frontend can append (display uses "; ")
        lead_teams_display = lead_teams_str.replace(";", "; ") if lead_teams_str else ""
        new_staff = {
            "id": staff_id,
            "hubspot_owner_id": str(owner_id),
            "name": name,
            "lead_teams": lead_teams_display,
            "availability": "Unavailable",
            "pause_leads": None,
            "max_pip_leads": None,
            "max_inbound_leads": None,
            "max_panther_leads": None,
            "max_frosties_leads": None,
            "open_pip_leads_n8n": None,
            "open_inbound_leads_n8n": None,
            "open_panther_leads": None,
            "open_frosties_leads": None,
            "on_holiday_today": False,
            "call_minutes_last_120": 0,
        }
        _hubspot_cache_set(
            "staff_created_cooldown",
            {"staff": new_staff, "until": time.time() + STAFF_CREATED_COOLDOWN_SECONDS},
        )
        _hubspot_cache_invalidate("staff", "lead_teams")
        out = {"staff": new_staff}
        if lead_teams_warning:
            out["lead_teams_warning"] = lead_teams_warning
        return jsonify(out), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Holidays (staff blocked dates) ---
@app.route("/api/holidays", methods=["GET"])
def api_list_holidays():
    try:
        staff_id = request.args.get("staff_id")
        from holidays import list_holidays
        holidays = list_holidays(staff_id=staff_id if staff_id else None)
        return jsonify({"holidays": holidays})
    except Exception as e:
        _log.exception("api_list_holidays failed")
        return _safe_json_response({"error": str(e) if e else "Unknown error", "holidays": []}, 500)


@app.route("/api/holidays", methods=["POST"])
def api_add_holiday():
    data = request.get_json() or {}
    staff_id = data.get("staff_id")
    start_date = data.get("start_date")
    end_date = data.get("end_date")
    label = data.get("label", "")
    if not staff_id:
        return jsonify({"error": "staff_id required"}), 400
    if not start_date or not end_date:
        return jsonify({"error": "start_date and end_date required"}), 400
    try:
        from holidays import add_holiday
        holiday = add_holiday(str(staff_id), start_date, end_date, label)
        return jsonify(holiday), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/holidays/<holiday_id>", methods=["PATCH"])
def api_update_holiday(holiday_id):
    data = request.get_json() or {}
    try:
        from holidays import update_holiday
        updated = update_holiday(
            holiday_id,
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            label=data.get("label"),
        )
        if updated is None:
            return jsonify({"error": "Holiday not found"}), 404
        return jsonify(updated)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/holidays/<holiday_id>", methods=["DELETE"])
def api_delete_holiday(holiday_id):
    try:
        from holidays import delete_holiday
        if delete_holiday(holiday_id):
            return jsonify({"ok": True}), 200
        return jsonify({"error": "Holiday not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/staff/field-options/<property_name>", methods=["GET"])
def get_staff_field_options(property_name):
    """Return dropdown options for a Staff object property (e.g. pause_leads) from HubSpot schema."""
    if not HUBSPOT_STAFF_OBJECT_ID:
        return jsonify({"options": []}), 200
    if property_name != "pause_leads":
        return jsonify({"options": []}), 200
    try:
        client = get_client()
        schema = client.get_custom_object_property(HUBSPOT_STAFF_OBJECT_ID, property_name)
        raw = schema.get("options") or []
        options = [
            {"value": o.get("value", ""), "label": o.get("label", o.get("value", ""))}
            for o in raw
            if isinstance(o, dict)
        ]
        return jsonify({"options": options})
    except Exception as e:
        app.logger.warning("Failed to fetch pause_leads options: %s", e)
        return jsonify({"options": []}), 200


@app.route("/api/staff/<object_id>", methods=["PATCH"])
def patch_staff(object_id):
    from config import HUBSPOT_STAFF_OBJECT_ID
    data = request.get_json() or {}
    availability = data.get("availability")
    pause_leads = data.get("pause_leads")
    add_team = data.get("add_team")
    remove_team = data.get("remove_team")
    try:
        client = get_client()
        if add_team is not None or remove_team is not None:
            team_val = add_team if add_team is not None else remove_team
            team_val = str(team_val).strip()
            if not team_val:
                return jsonify({"error": "add_team/remove_team cannot be empty"}), 400
            current = client.get_custom_object(
                HUBSPOT_STAFF_OBJECT_ID,
                object_id,
                properties=["lead_teams"],
            )
            props = current.get("properties") or {}
            raw = props.get("lead_teams")
            if isinstance(raw, dict) and "value" in raw:
                raw = raw["value"]
            current_teams = [t.strip() for t in (raw or "").split(";") if t.strip()]
            if add_team is not None:
                if team_val in current_teams:
                    return jsonify({"ok": True, "message": "already in team"})
                new_teams = current_teams + [team_val]
            else:
                new_teams = [t for t in current_teams if t != team_val]
            new_value = "; ".join(new_teams)
            client.patch_custom_object(
                HUBSPOT_STAFF_OBJECT_ID,
                object_id,
                {"lead_teams": new_value},
            )
            _hubspot_cache_invalidate("staff", "lead_teams")
            return jsonify({"ok": True})
        if availability is not None:
            client.patch_custom_object(
                HUBSPOT_STAFF_OBJECT_ID,
                object_id,
                {"availability": str(availability)},
            )
            _hubspot_cache_invalidate("staff", "lead_teams")
            return jsonify({"ok": True})
        if pause_leads is not None:
            client.patch_custom_object(
                HUBSPOT_STAFF_OBJECT_ID,
                object_id,
                {"pause_leads": str(pause_leads)},
            )
            _hubspot_cache_invalidate("staff", "lead_teams")
            return jsonify({"ok": True})
        return jsonify({"error": "provide availability, pause_leads, add_team, or remove_team"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Distribute: test run (all active staff, dry-run only) and single-owner (contact-based) ---
# Dry run can take a long time with many staff; run in background and poll for result
_dry_run_status = "idle"  # idle | running | done | error
_dry_run_result = None
_dry_run_error = None
_dry_run_lock = threading.Lock()


def _run_dry_run_background() -> None:
    """Run dry run in background; store result or error when done."""
    global _dry_run_status, _dry_run_result, _dry_run_error
    try:
        from distribution_engine import run_distribution_for_all_active
        result = run_distribution_for_all_active(dry_run=True)
        with _dry_run_lock:
            _dry_run_result = result
            _dry_run_error = None
            _dry_run_status = "done"
    except Exception as e:
        with _dry_run_lock:
            _dry_run_result = None
            _dry_run_error = str(e)
            _dry_run_status = "error"


@app.route("/api/distribute/test", methods=["POST"])
def distribute_test():
    """Start dry run in background; returns immediately to avoid request timeout."""
    global _dry_run_status, _dry_run_result, _dry_run_error
    with _dry_run_lock:
        if _dry_run_status == "running":
            return jsonify({"status": "already_running"}), 200
        _dry_run_status = "running"
        _dry_run_result = None
        _dry_run_error = None
    thread = threading.Thread(target=_run_dry_run_background, daemon=True, name="dry-run")
    thread.start()
    return jsonify({"status": "started"})


@app.route("/api/distribute/test/status", methods=["GET"])
def distribute_test_status():
    """Poll for dry run result (status: idle | running | done | error; result/error when done/error)."""
    with _dry_run_lock:
        status = _dry_run_status
        result = _dry_run_result
        error = _dry_run_error
    out = {"status": status}
    if result is not None:
        out["result"] = result
    if error is not None:
        out["error"] = error
    return jsonify(out)


@app.route("/api/distribute", methods=["POST"])
def distribute():
    data = request.get_json() or {}
    contact_id = data.get("contactId") or data.get("contact_id")
    dry_run = request.args.get("dry_run", "true").lower() in ("true", "1", "yes")
    if not contact_id:
        return jsonify({"error": "contactId required"}), 400
    try:
        from distribution_engine import run_distribution
        result = run_distribution(str(contact_id), dry_run=dry_run)
        if not dry_run and result.get("planned_assignments"):
            assignments = result["planned_assignments"]
            n = len(assignments)
            details = {
                "trigger_contact_id": contact_id,
                "assignments_count": n,
                "assignments": [
                    {"contact_id": a.get("contact_id"), "owner_id": a.get("owner_id"), "team": a.get("team")}
                    for a in assignments[:20]
                ],
            }
            _log_activity("assign", f"Assigned {n} contact(s) for contact {contact_id}", details)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Re-assign leads (redistribute another person's leads to available team members) ---
def _normalize_team(team: str):
    """Strip and match team against STAFF_LEAD_TEAMS; return exact name or None."""
    from config import STAFF_LEAD_TEAMS
    t = (team or "").strip()
    if not t:
        return None
    if t in STAFF_LEAD_TEAMS:
        return t
    # Case-insensitive fallback for staging/frontend quirks
    lower = t.lower()
    for name in STAFF_LEAD_TEAMS:
        if name.lower() == lower:
            return name
    return None


def _safe_json_response(data: dict, status: int = 200):
    """Return a JSON response that never raises (uses json.dumps with default=str)."""
    try:
        body = json.dumps(data, default=str)
        r = make_response(body, status)
        r.content_type = "application/json"
        return r
    except Exception:
        r = make_response(
            json.dumps({"error": "An unexpected error occurred. Please try again. Check deployment logs for details."}),
            500,
        )
        r.content_type = "application/json"
        return r


@app.route("/api/reassign/preview", methods=["GET"])
def reassign_preview():
    """GET ?owner_id=...&team=... (team = full name e.g. Inbound Lead Team). Returns counts and target_staff."""
    try:
        owner_id = (request.args.get("owner_id") or "").strip()
        team_raw = (request.args.get("team") or "").strip()
        if not owner_id or not team_raw:
            return _safe_json_response({"error": "owner_id and team required"}, 400)
        team = _normalize_team(team_raw)
        if not team:
            return _safe_json_response({"error": "invalid team"}, 400)
        from reassign import get_reassign_preview
        client = get_client()
        out = get_reassign_preview(client, owner_id, team)
        if out.get("error"):
            err = out["error"]
            if "429" in err or "Too Many Requests" in err:
                err = "HubSpot rate limit reached. Please wait a minute and try again."
            return _safe_json_response({"error": err}, 500)
        return _safe_json_response(out)
    except Exception as e:
        _log.exception("reassign preview failed")
        err_msg = str(e) if e else "Unknown error"
        if "429" in err_msg or "Too Many Requests" in err_msg:
            err_msg = "HubSpot rate limit reached. Please wait a minute and try again."
        return _safe_json_response({"error": err_msg}, 500)


@app.route("/api/reassign/execute", methods=["POST"])
def reassign_execute():
    """POST { owner_id, team, categories, target_owner_ids (optional) }. Reassigns contacts to selected staff only."""
    try:
        data = request.get_json(silent=True) or {}
        owner_id = (data.get("owner_id") or "").strip()
        team_raw = (data.get("team") or "").strip()
        categories = data.get("categories")
        if not isinstance(categories, list):
            categories = []
        categories = [c for c in categories if c in ("attempt_1", "attempt_2", "attempt_3", "call_back")]
        target_owner_ids = data.get("target_owner_ids")
        if isinstance(target_owner_ids, list):
            target_owner_ids = [str(o).strip() for o in target_owner_ids if o]
        else:
            target_owner_ids = None
        if not owner_id or not team_raw:
            return jsonify({"error": "owner_id and team required"}), 400
        if not categories:
            return jsonify({"error": "at least one category required"}), 400
        team = _normalize_team(team_raw)
        if not team:
            return jsonify({"error": "invalid team"}), 400
        from reassign import execute_reassign
        client = get_client()
        result = execute_reassign(client, owner_id, team, categories, target_owner_ids=target_owner_ids)
        if result.get("error"):
            return jsonify({"error": result["error"], "reassigned": 0, "assignments": []}), 400
        _log_activity(
            "reassign",
            f"Reassigned {result['reassigned']} lead(s) from {owner_id} ({team})",
            {"owner_id": owner_id, "team": team, "reassigned": result["reassigned"], "assignments": result["assignments"][:50]},
        )
        return jsonify({"reassigned": result["reassigned"], "assignments": result["assignments"]})
    except Exception as e:
        _log.exception("reassign execute failed")
        return jsonify({"error": str(e)}), 500


@app.route("/api/reassign/callbacks", methods=["GET"])
def reassign_callbacks():
    """GET ?owner_id=...&team=... Returns { callbacks: [...], target_staff: [...] } for Call Back Management."""
    try:
        owner_id = (request.args.get("owner_id") or "").strip()
        team_raw = (request.args.get("team") or "").strip()
        if not owner_id or not team_raw:
            return jsonify({"error": "owner_id and team required"}), 400
        team = _normalize_team(team_raw)
        if not team:
            return jsonify({"error": "invalid team"}), 400
        from reassign import list_callbacks
        client = get_client()
        out = list_callbacks(client, owner_id, team)
        return jsonify(out)
    except Exception as e:
        _log.exception("reassign callbacks failed")
        return jsonify({"error": str(e)}), 500


@app.route("/api/reassign/assign-one", methods=["POST"])
def reassign_assign_one():
    """POST { contact_id, new_owner_id, team }. Assigns a single contact to the new owner. team required so only same-team staff are allowed."""
    try:
        data = request.get_json(silent=True) or {}
        contact_id = (data.get("contact_id") or "").strip() or None
        new_owner_id = (data.get("new_owner_id") or "").strip() or None
        team_raw = (data.get("team") or "").strip() or None
        if not contact_id or not new_owner_id:
            return jsonify({"success": False, "error": "contact_id and new_owner_id required"}), 400
        if not team_raw:
            return jsonify({"success": False, "error": "team required"}), 400
        team = _normalize_team(team_raw)
        if not team:
            return jsonify({"success": False, "error": "invalid team"}), 400
        from reassign import assign_single_contact
        client = get_client()
        result = assign_single_contact(client, contact_id, new_owner_id, team_name=team)
        if not result.get("success"):
            return jsonify(result), 400
        _log_activity(
            "reassign",
            f"Reassigned 1 contact to {new_owner_id}",
            {"contact_id": contact_id, "new_owner_id": new_owner_id},
        )
        return jsonify(result)
    except Exception as e:
        _log.exception("reassign assign-one failed")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/redistribute/counts", methods=["GET"])
def api_redistribute_counts():
    """GET ?last_days= (optional), ?lead_type= (optional). Returns { counts: { reason: n, ... }, error?: string }. Uses DB cache when available (refreshed every 2h)."""
    try:
        from config import REDISTRIBUTE_LEAD_TYPES
        last_days = request.args.get("last_days")
        if last_days is not None and last_days != "":
            try:
                last_days = int(last_days)
                if last_days <= 0:
                    last_days = None
            except (TypeError, ValueError):
                last_days = None
        else:
            last_days = None
        lead_type = (request.args.get("lead_type") or "").strip() or None
        if lead_type is not None and lead_type not in REDISTRIBUTE_LEAD_TYPES:
            lead_type = None
        # Try cache first (never let cache path raise – fall back to HubSpot on any failure)
        if lead_type and _redistribute_cache_available and _redistribute_get_counts_from_cache:
            try:
                if _redistribute_cache_has_data():
                    out = _redistribute_get_counts_from_cache(lead_type, last_days)
                    if out is not None:
                        return jsonify(out)
            except Exception as cache_err:
                _log.debug("Redistribute cache fallback: %s", cache_err)
        from redistribute import get_redistribute_counts
        client = get_client()
        out = get_redistribute_counts(client, last_days=last_days, lead_type=lead_type)
        return jsonify(out)
    except Exception as e:
        _log.exception("redistribute counts failed")
        return jsonify({"counts": {}, "error": str(e)}), 500


@app.route("/api/redistribute/execute", methods=["POST"])
def api_redistribute_execute():
    """POST { reason, last_days?, lead_type? }. Re-distribute using DB cache when available (avoids HubSpot search)."""
    data = request.get_json() or {}
    reason = (data.get("reason") or "").strip()
    last_days = data.get("last_days")
    if last_days is not None and last_days != "":
        try:
            last_days = int(last_days)
            if last_days <= 0:
                last_days = None
        except (TypeError, ValueError):
            last_days = None
    else:
        last_days = None
    from config import REDISTRIBUTE_REASONS, REDISTRIBUTE_LEAD_TYPES
    lead_type = (data.get("lead_type") or "").strip() or None
    if lead_type is not None and lead_type not in REDISTRIBUTE_LEAD_TYPES:
        lead_type = None
    if not reason or reason not in REDISTRIBUTE_REASONS:
        return jsonify({"error": "reason required and must be one of: " + ", ".join(REDISTRIBUTE_REASONS)}), 400
    try:
        client = get_client()
        if lead_type and _redistribute_cache_available and _redistribute_get_lead_rows_from_cache:
            try:
                if _redistribute_cache_has_data():
                    rows = _redistribute_get_lead_rows_from_cache(lead_type, reason, last_days)
                    if rows is not None:
                        from redistribute import execute_redistribute_batch
                        result = execute_redistribute_batch(client, rows)
                        lead_ids_done = result.get("lead_ids") or []
                        if lead_ids_done and _redistribute_remove_lead_ids_from_cache:
                            _redistribute_remove_lead_ids_from_cache(lead_ids_done)
                        _log_activity(
                            "redistribute",
                            f"Re-distributed {result['redistributed']} lead(s) (reason: {reason}, from cache)",
                            {"reason": reason, "redistributed": result["redistributed"], "errors": result.get("errors", [])[:20]},
                        )
                        return jsonify({"redistributed": result["redistributed"], "errors": result.get("errors", [])})
            except Exception as cache_err:
                _log.debug("Redistribute execute cache fallback: %s", cache_err)
        from redistribute import execute_redistribute
        result = execute_redistribute(client, reason, last_days=last_days, lead_type=lead_type)
        if result.get("error"):
            return jsonify({"redistributed": result.get("redistributed", 0), "errors": result.get("errors", []), "error": result["error"]}), 400
        lead_ids_done = result.get("lead_ids") or []
        if lead_ids_done and _redistribute_remove_lead_ids_from_cache:
            _redistribute_remove_lead_ids_from_cache(lead_ids_done)
        _log_activity(
            "redistribute",
            f"Re-distributed {result['redistributed']} lead(s) (reason: {reason})",
            {"reason": reason, "redistributed": result["redistributed"], "errors": result.get("errors", [])[:20]},
        )
        return jsonify({"redistributed": result["redistributed"], "errors": result.get("errors", [])})
    except Exception as e:
        _log.exception("redistribute execute failed")
        return jsonify({"redistributed": 0, "errors": [], "error": str(e)}), 500


@app.route("/api/redistribute/lead-lookup", methods=["GET"])
def api_redistribute_lead_lookup():
    """GET ?lead_id=... Returns { lead_id, lead_name, contact_id?, error? } for single-lead re-distribute confirmation."""
    lead_id = (request.args.get("lead_id") or "").strip()
    if not lead_id:
        return jsonify({"lead_id": "", "lead_name": "", "contact_id": None, "error": "lead_id is required"}), 400
    try:
        from redistribute import lookup_lead_for_redistribute
        client = get_client()
        out = lookup_lead_for_redistribute(client, lead_id)
        if out.get("error"):
            return jsonify(out), 400
        return jsonify(out)
    except Exception as e:
        _log.exception("redistribute lead-lookup failed")
        return _safe_json_response({"lead_id": lead_id, "lead_name": "", "contact_id": None, "error": str(e)}, 500)


@app.route("/api/redistribute/execute-one", methods=["POST"])
def api_redistribute_execute_one():
    """POST { lead_id }. Re-distribute a single lead (contact owner cleared, lead moved to new stage)."""
    data = request.get_json(silent=True) or {}
    lead_id = (data.get("lead_id") or "").strip()
    if not lead_id:
        return jsonify({"success": False, "error": "lead_id is required", "contact_updated": False, "lead_updated": False}), 400
    try:
        from redistribute import execute_single_lead_redistribute
        client = get_client()
        result = execute_single_lead_redistribute(client, lead_id)
        if result.get("success") and _redistribute_remove_lead_ids_from_cache:
            _redistribute_remove_lead_ids_from_cache([lead_id])
        if result.get("success"):
            _log_activity("redistribute_one", f"Re-distributed single lead {lead_id}", {"lead_id": lead_id})
        status = 200 if result.get("success") else 400
        return jsonify(result), status
    except Exception as e:
        _log.exception("redistribute execute-one failed")
        return _safe_json_response({"success": False, "error": str(e), "contact_updated": False, "lead_updated": False}, 500)


# 500 error handler returns same JSON fallback (body defined at top)
@app.errorhandler(500)
def api_500_json(e):
    path = ""
    try:
        if request:
            path = getattr(request, "path", "") or ""
    except Exception:
        pass
    if path.startswith("/api/"):
        r = make_response(_API_500_JSON_BODY, 500)
        r.content_type = "application/json"
        return r
    raise e  # non-API: let Flask's default 500 response run


# --- Serve frontend ---
@app.route("/")
def index():
    folder = app.static_folder or ""
    index_path = os.path.join(folder, "index.html")
    if folder and os.path.isfile(index_path):
        return send_from_directory(folder, "index.html")
    return "<p>Kinly Lead Distribution API. Dashboard not found (missing frontend/index.html).</p>"


@app.route("/<path:filename>")
def frontend_static(filename):
    """Serve frontend assets (style.css, app.js) from frontend/."""
    folder = app.static_folder or ""
    if not folder:
        return jsonify({"error": "Not found"}), 404
    safe_path = os.path.normpath(filename)
    if safe_path.startswith("..") or os.path.isabs(safe_path):
        return jsonify({"error": "Not found"}), 404
    path = os.path.join(folder, safe_path)
    if not os.path.isfile(path):
        return jsonify({"error": "Not found"}), 404
    return send_from_directory(folder, safe_path)


def _refresh_loop() -> None:
    """Background loop: wait 6 minutes, run periodic refresh, repeat."""
    time.sleep(60)  # First run after 1 minute so startup isn't slammed
    while True:
        try:
            run_periodic_refresh()
        except Exception as e:
            _log.exception("Refresh loop error: %s", e)
        time.sleep(REFRESH_INTERVAL_SECONDS)


if ENABLE_BACKGROUND_DISTRIBUTION:
    _refresh_thread = threading.Thread(target=_refresh_loop, daemon=True, name="kinly-refresh")
    _refresh_thread.start()
    _log.info("Background lead distribution enabled (periodic refresh every 6 min)")
else:
    _log.info("Background lead distribution disabled (ENABLE_BACKGROUND_DISTRIBUTION=false)")


def _cache_warmer_loop() -> None:
    """Background loop: wait 15s, then warm HubSpot cache every 2 min so dashboard loads are fast."""
    time.sleep(15)
    while True:
        try:
            _warm_hubspot_cache()
        except Exception as e:
            _log.warning("Cache warmer error: %s", e)
        time.sleep(120)


if os.getenv("DATABASE_URL"):
    _warmer_thread = threading.Thread(target=_cache_warmer_loop, daemon=True, name="cache-warmer")
    _warmer_thread.start()
    _log.info("HubSpot cache warmer started (runs every 2 min)")


def _redistribute_cache_loop() -> None:
    """Background loop: wait 2 min, then refresh unqualified leads cache every 2 hours (configurable)."""
    from config import REDISTRIBUTE_CACHE_REFRESH_INTERVAL_SECONDS
    time.sleep(120)  # First run 2 min after startup
    while True:
        try:
            if _redistribute_cache_available and _refresh_redistribute_cache_fn and HUBSPOT_ACCESS_TOKEN:
                client = get_client()
                _refresh_redistribute_cache_fn(client)
        except Exception as e:
            _log.exception("Redistribute cache refresh error: %s", e)
        time.sleep(REDISTRIBUTE_CACHE_REFRESH_INTERVAL_SECONDS)


if os.getenv("DATABASE_URL"):
    _redistribute_cache_thread = threading.Thread(target=_redistribute_cache_loop, daemon=True, name="redistribute-cache")
    _redistribute_cache_thread.start()
    _log.info("Redistribute cache refresh started (every 2 hours)" if _redistribute_cache_available else "Redistribute cache disabled (table/DB unavailable)")

if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", 5001))
    debug = os.getenv("FLASK_DEBUG", "").lower() in ("1", "true", "yes")
    app.run(host="0.0.0.0", port=port, debug=debug)
