"""
Re-assign leads: redistribute another person's leads to available staff in the same team.
Leads are filtered by pipeline stage (new, attempting, connected); categorized by
Attempt 1/2/3 (hs_tag_ids) and Call Back (call_back_date future). Reassignment is done
by assigning the Contact associated with each Lead to the new owner (staff's hubspot_owner_id).
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from hubspot_client import HubSpotClient
from config import (
    HUBSPOT_STAFF_OBJECT_ID,
    HS_LEAD_TYPE_BY_TEAM,
    REASSIGN_PIPELINE_STAGES,
    REASSIGN_CALL_BACK_DATE_PROPERTY,
    REASSIGN_TAG_ATTEMPT_1,
    REASSIGN_TAG_ATTEMPT_2,
    REASSIGN_TAG_ATTEMPT_3,
)

_log = logging.getLogger(__name__)

# Category keys for API/frontend
CATEGORY_ATTEMPT_1 = "attempt_1"
CATEGORY_ATTEMPT_2 = "attempt_2"
CATEGORY_ATTEMPT_3 = "attempt_3"
CATEGORY_CALL_BACK = "call_back"
ALL_CATEGORIES = [CATEGORY_ATTEMPT_1, CATEGORY_ATTEMPT_2, CATEGORY_ATTEMPT_3, CATEGORY_CALL_BACK]


def _prop_value(props: dict, key: str) -> Any:
    p = props.get(key)
    if p is None:
        return None
    if isinstance(p, dict) and "value" in p:
        return p["value"]
    return p


def _str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _parse_tag_ids(raw: Any) -> set[str]:
    """Parse hs_tag_ids (may be semicolon-separated or single value). Return set of tag ID strings."""
    if raw is None:
        return set()
    s = _str(raw)
    if not s:
        return set()
    return set(t.strip() for t in s.replace(";", ",").split(",") if t.strip())


def _parse_date(raw: Any) -> date | None:
    """Parse call_back_date to date. Return None if invalid or missing."""
    if raw is None:
        return None
    s = _str(raw)
    if not s or len(s) < 10:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _is_future(d: date | None) -> bool:
    if d is None:
        return False
    return d > date.today()


def _categorize_lead(lead: dict) -> list[str]:
    """
    Return list of categories this lead belongs to.
    If call_back_date is future -> only 'call_back'. Else -> attempt_1/2/3 based on hs_tag_ids.
    """
    props = lead.get("properties") or {}
    tag_ids = _parse_tag_ids(_prop_value(props, "hs_tag_ids"))
    call_back = _parse_date(_prop_value(props, REASSIGN_CALL_BACK_DATE_PROPERTY))

    if _is_future(call_back):
        return [CATEGORY_CALL_BACK]

    categories = []
    if REASSIGN_TAG_ATTEMPT_1 in tag_ids:
        categories.append(CATEGORY_ATTEMPT_1)
    if REASSIGN_TAG_ATTEMPT_2 in tag_ids:
        categories.append(CATEGORY_ATTEMPT_2)
    if REASSIGN_TAG_ATTEMPT_3 in tag_ids:
        categories.append(CATEGORY_ATTEMPT_3)
    return categories


def _fetch_leads_for_owner_team(
    client: HubSpotClient,
    owner_id: str,
    team_name: str,
) -> list[dict]:
    """Fetch leads for this owner and team (hs_lead_type), in allowed pipeline stages only."""
    hs_lead_type = HS_LEAD_TYPE_BY_TEAM.get(team_name)
    if not hs_lead_type:
        return []

    # HubSpot search: IN with multiple values for pipeline stage
    filters = [
        {"propertyName": "hubspot_owner_id", "operator": "EQ", "value": owner_id},
        {"propertyName": "hs_lead_type", "operator": "EQ", "value": hs_lead_type},
    ]
    if len(REASSIGN_PIPELINE_STAGES) == 1:
        filters.append({
            "propertyName": "hs_pipeline_stage",
            "operator": "EQ",
            "value": REASSIGN_PIPELINE_STAGES[0],
        })
    else:
        filters.append({
            "propertyName": "hs_pipeline_stage",
            "operator": "IN",
            "values": REASSIGN_PIPELINE_STAGES,
        })

    props_needed = ["hs_tag_ids", REASSIGN_CALL_BACK_DATE_PROPERTY, "hs_pipeline_stage"]
    all_results = []
    after = None
    while True:
        res = client.search_leads(
            filter_groups=[{"filters": filters}],
            properties=props_needed,
            limit=100,
            after=after,
        )
        results = res.get("results", [])
        all_results.extend(results)
        after = (res.get("paging") or {}).get("next", {}).get("after")
        if not after or len(results) < 100:
            break
    return all_results


def get_reassign_preview(
    client: HubSpotClient,
    owner_id: str,
    team_name: str,
) -> dict:
    """
    Returns counts per category (attempt_1, attempt_2, attempt_3, call_back) and
    target_staff (same team, available, excluding owner_id).
    """
    counts = {CATEGORY_ATTEMPT_1: 0, CATEGORY_ATTEMPT_2: 0, CATEGORY_ATTEMPT_3: 0, CATEGORY_CALL_BACK: 0}
    leads = _fetch_leads_for_owner_team(client, owner_id, team_name)
    for lead in leads:
        for cat in _categorize_lead(lead):
            if cat in counts:
                counts[cat] += 1

    # Target staff: same team, availability = Available, exclude owner_id
    target_staff = _get_target_staff(client, team_name, exclude_owner_id=owner_id)
    return {"counts": counts, "target_staff": target_staff}


def _staff_in_team(lead_teams_raw: Any, team_name: str) -> bool:
    """Check if staff's lead_teams (multi-select) contains team_name."""
    s = _str(lead_teams_raw)
    if not s:
        return False
    parts = [p.strip() for p in s.replace(";", ",").split(",") if p.strip()]
    return team_name in parts


def _num(v: Any) -> int:
    if v is None:
        return 0
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _get_target_staff(
    client: HubSpotClient,
    team_name: str,
    exclude_owner_id: str,
) -> list[dict]:
    """Staff in team_name with availability Available, excluding exclude_owner_id. Includes total_open_leads; sorted by most leads first."""
    result = client.search_custom_objects(
        HUBSPOT_STAFF_OBJECT_ID,
        filter_groups=[{"filters": [{"propertyName": "hubspot_owner_id", "operator": "HAS_PROPERTY"}]}],
        properties=[
            "hubspot_owner_id", "name", "lead_teams", "availability",
            "open_inbound_leads_n8n", "open_pip_leads_n8n", "open_panther_leads", "open_frosties_leads",
        ],
        limit=200,
    )
    rows = result.get("results", []) or []
    from holidays import is_staff_on_holiday_today
    out = []
    for r in rows:
        props = r.get("properties") or {}
        owner_id = _str(_prop_value(props, "hubspot_owner_id"))
        if owner_id == exclude_owner_id:
            continue
        if not _staff_in_team(_prop_value(props, "lead_teams"), team_name):
            continue
        availability = _str(_prop_value(props, "availability"))
        if availability == "Unavailable":
            continue
        staff_id = r.get("id")
        if staff_id and is_staff_on_holiday_today(str(staff_id)):
            continue
        name = _str(_prop_value(props, "name")) or owner_id
        total_open = (
            _num(_prop_value(props, "open_inbound_leads_n8n"))
            + _num(_prop_value(props, "open_pip_leads_n8n"))
            + _num(_prop_value(props, "open_panther_leads"))
            + _num(_prop_value(props, "open_frosties_leads"))
        )
        out.append({
            "id": str(staff_id),
            "hubspot_owner_id": owner_id,
            "name": name,
            "total_open_leads": total_open,
        })
    out.sort(key=lambda x: x.get("total_open_leads", 0))  # least leads first
    return out


def execute_reassign(
    client: HubSpotClient,
    owner_id: str,
    team_name: str,
    categories: list[str],
    target_owner_ids: list[str] | None = None,
) -> dict:
    """
    Select leads in the given categories, resolve Lead->Contact, distribute contacts
    to target staff (round-robin). If target_owner_ids is provided, only those owners
    receive leads. PATCH each contact's hubspot_owner_id. Returns { "reassigned": n, "assignments": [...], "error": optional }.
    """
    if not categories:
        return {"reassigned": 0, "assignments": [], "error": "No categories selected"}

    leads = _fetch_leads_for_owner_team(client, owner_id, team_name)
    selected_lead_ids = []
    for lead in leads:
        lead_cats = _categorize_lead(lead)
        if any(c in categories for c in lead_cats):
            selected_lead_ids.append(lead.get("id"))

    if not selected_lead_ids:
        return {"reassigned": 0, "assignments": [], "error": None}

    # Resolve Lead -> Contact
    assoc = client.get_lead_to_contact_associations_batch(selected_lead_ids)
    contact_ids = []
    seen = set()
    for lid in selected_lead_ids:
        for cid in assoc.get(str(lid), []):
            if cid and cid not in seen:
                seen.add(cid)
                contact_ids.append(cid)

    if not contact_ids:
        return {"reassigned": 0, "assignments": [], "error": "No associated contacts found for selected leads"}

    target_staff = _get_target_staff(client, team_name, exclude_owner_id=owner_id)
    if target_owner_ids is not None:
        allowed = set(target_owner_ids)
        target_staff = [s for s in target_staff if s.get("hubspot_owner_id") in allowed]
    if not target_staff:
        return {"reassigned": 0, "assignments": [], "error": "No staff selected to receive leads"}

    # Order by fewest open leads first so they get first pick; then cycle through the list
    target_staff = sorted(target_staff, key=lambda x: x.get("total_open_leads", 0))

    # Assign one contact at a time, cycling through staff (least leads → next → … → back to first)
    assignments = []
    for i, cid in enumerate(contact_ids):
        staff = target_staff[i % len(target_staff)]
        new_owner_id = staff["hubspot_owner_id"]
        client.patch_contact(cid, {"hubspot_owner_id": new_owner_id, "assign_lead": "Yes"})
        assignments.append({
            "contact_id": cid,
            "owner_id": new_owner_id,
            "staff_name": staff["name"],
        })

    return {"reassigned": len(assignments), "assignments": assignments, "error": None}
