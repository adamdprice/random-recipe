"""
Kinly Lead Distribution - Flask backend.
Serves frontend static files and all /api routes.
"""
import os
import threading
from flask import Flask, request, jsonify, send_from_directory, redirect, session

from config import (
    HUBSPOT_ACCESS_TOKEN,
    HUBSPOT_STAFF_OBJECT_ID,
    HUBSPOT_LEAD_TEAM_OBJECT_ID,
    SESSION_SECRET,
)
import hubspot_client as hc
import holidays as holidays_mod
import activity_log as activity_log_mod
from auth import (
    send_otp,
    verify_otp,
    login_user,
    logout_user,
    current_user,
    login_required,
    is_allowed_email,
)
from distribution_engine import run_dry_run

app = Flask(__name__, static_folder="frontend", static_url_path="")
app.secret_key = SESSION_SECRET
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = 2592000  # 30 days
if os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("FLASK_ENV") == "production":
    app.config["SESSION_COOKIE_SECURE"] = True

# Optional: ensure frontend paths
FRONTEND = os.path.join(os.path.dirname(__file__), "frontend")


def _staff_with_holiday(staff_list):
    for s in staff_list:
        s["on_holiday_today"] = holidays_mod.is_on_holiday_today(str(s.get("id") or ""))
    return staff_list


# ---------- Static and login page ----------
@app.route("/")
def index():
    if not current_user():
        return redirect("/login")
    return send_from_directory(FRONTEND, "index.html")


@app.route("/login", methods=["GET"])
def login_page():
    if current_user():
        return redirect("/")
    return send_from_directory(FRONTEND, "login.html")


@app.route("/style.css")
def style_css():
    return send_from_directory(FRONTEND, "style.css")


@app.route("/app.js")
def app_js():
    return send_from_directory(FRONTEND, "app.js")


@app.route("/images/<path:filename>")
def images(filename):
    return send_from_directory(os.path.join(FRONTEND, "images"), filename)


# ---------- Auth API ----------
@app.route("/api/login", methods=["POST"])
def api_login_send():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    if not email:
        return jsonify({"error": "Email required"}), 400
    err = send_otp(email)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"sent": True})


@app.route("/api/login/verify", methods=["POST"])
def api_login_verify():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    code = (data.get("code") or "").strip()
    if not email or not code:
        return jsonify({"error": "Email and code required"}), 400
    if not verify_otp(email, code):
        return jsonify({"error": "Invalid or expired code"}), 400
    login_user(email)
    return jsonify({"ok": True})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    logout_user()
    return jsonify({"ok": True})


# ---------- Health (no auth) ----------
@app.route("/api/health")
def api_health():
    ok = bool(HUBSPOT_ACCESS_TOKEN)
    try:
        if ok:
            hc.test_connection()
    except Exception:
        ok = False
    return jsonify({"hubspot_configured": ok})


# ---------- Staff ----------
@app.route("/api/staff", methods=["GET"])
@login_required
def api_staff_list():
    try:
        staff = hc.get_all_staff()
        staff = _staff_with_holiday(staff)
        return jsonify({"staff": staff})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/staff/field-options/pause_leads")
@login_required
def api_staff_field_options_pause_leads():
    # Static options; can be moved to config or HubSpot enum
    options = [
        {"value": "Paused", "label": "Paused"},
        {"value": "Busy", "label": "Busy"},
        {"value": "Other", "label": "Other"},
    ]
    return jsonify({"options": options})


def _parse_lead_teams(s: str):
    if not s or not isinstance(s, str):
        return []
    return [t.strip() for t in s.split(";") if t.strip()]


def _format_lead_teams(teams: list):
    return "; ".join(teams)


@app.route("/api/staff", methods=["POST"])
@login_required
def api_staff_create():
    data = request.get_json() or {}
    owner_id = (data.get("hubspot_owner_id") or "").strip()
    lead_teams = data.get("lead_teams") or []
    if not owner_id:
        return jsonify({"error": "hubspot_owner_id required"}), 400
    if not HUBSPOT_STAFF_OBJECT_ID:
        return jsonify({"error": "Staff object not configured"}), 500
    try:
        props = {
            "hubspot_owner_id": owner_id,
            "availability": "Available",
            "lead_teams": _format_lead_teams(lead_teams) if isinstance(lead_teams, list) else str(lead_teams),
        }
        created = hc.create_custom_object(HUBSPOT_STAFF_OBJECT_ID, props)
        staff_id = created.get("id")
        staff = hc.get_staff_by_id(staff_id) if staff_id else None
        if staff:
            staff["on_holiday_today"] = holidays_mod.is_on_holiday_today(str(staff_id))
        lead_teams_warning = None
        return jsonify({"staff": staff or created}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/staff/<staff_id>", methods=["PATCH"])
@login_required
def api_staff_patch(staff_id):
    data = request.get_json() or {}
    if not HUBSPOT_STAFF_OBJECT_ID:
        return jsonify({"error": "Staff object not configured"}), 500
    try:
        staff = hc.get_staff_by_id(staff_id)
        if not staff:
            return jsonify({"error": "Staff not found"}), 404
        props = {}
        if "availability" in data:
            props["availability"] = str(data["availability"])
        if "pause_leads" in data:
            props["pause_leads"] = str(data["pause_leads"]).strip() or ""
        if "add_team" in data:
            teams = _parse_lead_teams(staff.get("lead_teams") or "")
            add = (data.get("add_team") or "").strip()
            if add and add not in teams:
                teams.append(add)
            props["lead_teams"] = _format_lead_teams(teams)
        if "remove_team" in data:
            teams = _parse_lead_teams(staff.get("lead_teams") or "")
            remove = (data.get("remove_team") or "").strip()
            teams = [t for t in teams if t != remove]
            props["lead_teams"] = _format_lead_teams(teams)
        if not props:
            return jsonify(staff)
        hc.patch_custom_object(HUBSPOT_STAFF_OBJECT_ID, staff_id, props)
        updated = hc.get_staff_by_id(staff_id)
        if updated:
            updated["on_holiday_today"] = holidays_mod.is_on_holiday_today(str(staff_id))
        return jsonify(updated or staff)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


_refresh_running = False
_refresh_result = None


@app.route("/api/staff/refresh-leads", methods=["POST"])
@login_required
def api_staff_refresh_leads():
    global _refresh_running, _refresh_result
    if _refresh_running:
        return jsonify({"status": "already_running"})
    def run():
        global _refresh_running, _refresh_result
        _refresh_running = True
        _refresh_result = None
        try:
            staff = hc.get_all_staff()
            activity_log_mod.log("refresh_leads", "Manual refresh completed", {"updated": len(staff)})
            _refresh_result = {"updated": len(staff), "errors": []}
        except Exception as e:
            activity_log_mod.log("refresh_error", str(e), {})
            _refresh_result = {"updated": 0, "errors": [{"error": str(e)}]}
        finally:
            _refresh_running = False
    threading.Thread(target=run).start()
    return jsonify({"status": "started"})


# ---------- Lead teams ----------
@app.route("/api/lead-teams", methods=["GET"])
@login_required
def api_lead_teams_list():
    try:
        if not HUBSPOT_LEAD_TEAM_OBJECT_ID:
            return jsonify({"lead_teams": [], "message": "Lead teams not configured"})
        teams = hc.get_all_lead_teams()
        return jsonify({"lead_teams": teams})
    except Exception as e:
        return jsonify({"error": str(e), "lead_teams": []})


@app.route("/api/lead-teams/<team_id>", methods=["PATCH"])
@login_required
def api_lead_teams_patch(team_id):
    data = request.get_json() or {}
    max_leads = data.get("max_leads")
    if max_leads is None:
        return jsonify({"error": "max_leads required"}), 400
    try:
        hc.patch_lead_team(team_id, int(max_leads))
        teams = hc.get_all_lead_teams()
        one = next((t for t in teams if str(t.get("id")) == str(team_id)), None)
        return jsonify(one or {"id": team_id, "max_leads": max_leads})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- Holidays ----------
@app.route("/api/holidays", methods=["GET"])
@login_required
def api_holidays_list():
    return jsonify({"holidays": holidays_mod.all_holidays()})


@app.route("/api/holidays", methods=["POST"])
@login_required
def api_holidays_create():
    data = request.get_json() or {}
    staff_id = (data.get("staff_id") or "").strip()
    start_date = (data.get("start_date") or "").strip()
    end_date = (data.get("end_date") or "").strip()
    label = (data.get("label") or "").strip()
    if not staff_id or not start_date or not end_date:
        return jsonify({"error": "staff_id, start_date, end_date required"}), 400
    rec = holidays_mod.add_holiday(staff_id, start_date, end_date, label)
    return jsonify(rec), 201


@app.route("/api/holidays/<holiday_id>", methods=["PATCH"])
@login_required
def api_holidays_update(holiday_id):
    data = request.get_json() or {}
    rec = holidays_mod.update_holiday(
        holiday_id,
        (data.get("staff_id") or "").strip(),
        (data.get("start_date") or "").strip(),
        (data.get("end_date") or "").strip(),
        (data.get("label") or "").strip(),
    )
    if not rec:
        return jsonify({"error": "Holiday not found"}), 404
    return jsonify(rec)


@app.route("/api/holidays/<holiday_id>", methods=["DELETE"])
@login_required
def api_holidays_delete(holiday_id):
    if not holidays_mod.delete_holiday(holiday_id):
        return jsonify({"error": "Holiday not found"}), 404
    return jsonify({"ok": True})


# ---------- Activity log ----------
@app.route("/api/activity-log")
@login_required
def api_activity_log():
    limit = request.args.get("limit", 50, type=int)
    limit = min(max(limit, 1), 200)
    entries = activity_log_mod.get_entries(limit)
    return jsonify({"entries": entries})


# ---------- Owners ----------
@app.route("/api/owners")
@login_required
def api_owners():
    try:
        owners = hc.list_owners()
        return jsonify({"owners": owners})
    except Exception as e:
        return jsonify({"error": str(e), "owners": []})


# ---------- Distribute test (dry run) ----------
_dry_run_status = None
_dry_run_lock = threading.Lock()


@app.route("/api/distribute/test", methods=["POST"])
@login_required
def api_distribute_test():
    global _dry_run_status
    with _dry_run_lock:
        if _dry_run_status == "running":
            return jsonify({"status": "already_running"})
        _dry_run_status = "running"
    try:
        result = run_dry_run()
        with _dry_run_lock:
            _dry_run_status = {"status": "done", "result": result}
        # Frontend accepts full result in response too
        return jsonify(result)
    except Exception as e:
        with _dry_run_lock:
            _dry_run_status = {"status": "error", "error": str(e)}
        return jsonify({"error": str(e)}), 500
    finally:
        with _dry_run_lock:
            if _dry_run_status == "running":
                _dry_run_status = None


@app.route("/api/distribute/test/status")
@login_required
def api_distribute_test_status():
    with _dry_run_lock:
        s = _dry_run_status
    if s is None:
        return jsonify({"status": "done", "result": None})
    if s == "running":
        return jsonify({"status": "running"})
    if isinstance(s, dict):
        return jsonify(s)
    return jsonify({"status": "done", "result": None})


# ---------- Run ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
