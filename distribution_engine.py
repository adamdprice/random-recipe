"""
Distribution engine: replicates N8N Kinly Lead Smart Distribution.
Run for a contact's owner: compute deltas and either execute assignments (live) or return planned actions (dry_run).
"""
import math
import time
from typing import Any, Optional, Set

from hubspot_client import HubSpotClient
from config import (
    HUBSPOT_STAFF_OBJECT_ID,
    HUBSPOT_LEAD_PIPELINE_STAGE,
    LEAD_PRIORITY_BY_TYPE,
    HS_LEAD_TYPES,
)


def _prop_value(props: dict, key: str) -> Any:
    """Get value from HubSpot property (may be { value: x } or raw)."""
    p = props.get(key)
    if p is None:
        return None
    if isinstance(p, dict) and "value" in p:
        return p["value"]
    return p


def _num(v: Any) -> int:
    if v is None:
        return 0
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def get_total_assigned_contacts_for_owner(client: HubSpotClient, owner_id: str) -> int:
    """Count contacts currently assigned to this owner (source of truth for total capacity)."""
    res = client.search_contacts(
        filter_groups=[{
            "filters": [{"propertyName": "hubspot_owner_id", "operator": "EQ", "value": owner_id}],
        }],
        properties=["hubspot_owner_id"],
        limit=1,
    )
    return res.get("total", 0) or 0


def get_open_lead_counts_for_owner(client: HubSpotClient, owner_id: str) -> dict:
    """Count open leads per type for the given hubspot_owner_id (from Leads object)."""
    def count_open_leads(lead_type_value: str) -> int:
        res = client.search_leads(
            filter_groups=[{
                "filters": [
                    {"propertyName": "hs_pipeline_stage", "operator": "EQ", "value": HUBSPOT_LEAD_PIPELINE_STAGE},
                    {"propertyName": "hubspot_owner_id", "operator": "EQ", "value": owner_id},
                    {"propertyName": "hs_lead_type", "operator": "EQ", "value": lead_type_value},
                ],
            }],
            properties=["hs_pipeline_stage", "hubspot_owner_id"],
            limit=200,
        )
        return res.get("total", 0) or len(res.get("results", []))

    return {
        "open_inbound_leads_n8n": count_open_leads(HS_LEAD_TYPES["inbound"]),
        "open_pip_leads_n8n": count_open_leads(HS_LEAD_TYPES["pip"]),
        "open_frosties_leads": count_open_leads(HS_LEAD_TYPES["frosties"]),
        "open_panther_leads": count_open_leads(HS_LEAD_TYPES["panther"]),
    }


def refresh_staff_open_leads() -> dict:
    """
    Recalculate and update open lead counts for all staff members.
    Returns { "updated": n, "errors": [ ... ] }.
    """
    client = HubSpotClient()
    result = client.search_custom_objects(
        HUBSPOT_STAFF_OBJECT_ID,
        filter_groups=[{"filters": [{"propertyName": "hubspot_owner_id", "operator": "HAS_PROPERTY"}]}],
        properties=["hubspot_owner_id"],
        limit=100,
    )
    rows = result.get("results", []) if isinstance(result, dict) else []
    updated = 0
    errors = []
    for i, r in enumerate(rows):
        if i > 0:
            time.sleep(0.25)  # Reduce HubSpot rate-limit errors when refreshing many staff
        staff_id = r.get("id")
        props = r.get("properties") or {}
        raw = props.get("hubspot_owner_id")
        if isinstance(raw, dict) and "value" in raw:
            raw = raw["value"]
        owner_id = (raw or "").strip()
        if not owner_id or not staff_id:
            continue
        last_error = None
        for attempt in range(3):
            try:
                counts = get_open_lead_counts_for_owner(client, owner_id)
                client.patch_custom_object(HUBSPOT_STAFF_OBJECT_ID, str(staff_id), counts)
                updated += 1
                last_error = None
                break
            except Exception as e:
                last_error = e
                err_str = str(e)
                if "429" in err_str or "rate" in err_str.lower():
                    time.sleep(2.0 * (attempt + 1))
                else:
                    break
        if last_error is not None:
            errors.append({"staff_id": staff_id, "owner_id": owner_id, "error": str(last_error)})
    return {"updated": updated, "errors": errors}


def _run_distribution_for_owner(
    client: HubSpotClient,
    owner_id: str,
    dry_run: bool = True,
    staff_name: Optional[str] = None,
    assigned_this_run: Optional[Set[str]] = None,
) -> dict:
    """
    Run distribution for a single owner (by hubspot_owner_id).
    No contact lookup; used for "run for all active" and by run_distribution.
    If assigned_this_run is provided (e.g. from run_distribution_for_all_active), contacts
    already allocated in this run are skipped so the same contact is never assigned twice.
    Returns dict with planned_assignments, planned_staff_updates, summary, and optional error.
    """
    planned_assignments = []
    planned_staff_updates = []

    # 1) Count open leads per type for this owner
    counts = get_open_lead_counts_for_owner(client, owner_id)
    open_inbound = counts["open_inbound_leads_n8n"]
    open_pip = counts["open_pip_leads_n8n"]
    open_frosties = counts["open_frosties_leads"]
    open_panther = counts["open_panther_leads"]

    # 2) Get Staff Member by hubspot_owner_id
    staff_result = client.get_staff_by_owner_id(owner_id, HUBSPOT_STAFF_OBJECT_ID)
    results = staff_result.get("results", [])
    if not results:
        return {
            "owner_id": owner_id,
            "staff_name": staff_name,
            "error": "No staff member found for this owner",
            "planned_assignments": [],
            "planned_staff_updates": [],
            "summary": {"assignments_count": 0, "staff_updates_count": 0},
        }
    staff_row = results[0]
    staff_id = staff_row.get("id")
    staff_props = staff_row.get("properties", {})

    lead_teams_raw = _str(_prop_value(staff_props, "lead_teams"))
    lead_teams_list = [t.strip() for t in lead_teams_raw.split(";") if t.strip()]
    team_count = len(lead_teams_list) if lead_teams_list else 1

    def _ceil_div(a: int, b: int) -> int:
        if b <= 0:
            return 0
        return int(math.ceil(a / b))

    max_pip = _num(_prop_value(staff_props, "max_pip_leads"))
    max_inbound = _num(_prop_value(staff_props, "max_inbound_leads"))
    max_panther = _num(_prop_value(staff_props, "max_panther_leads"))
    max_frosties = _num(_prop_value(staff_props, "max_frosties_leads"))

    alloc_pip = _ceil_div(max_pip, team_count)
    alloc_inbound = _ceil_div(max_inbound, team_count)
    alloc_panther = _ceil_div(max_panther, team_count)
    alloc_frosties = _ceil_div(max_frosties, team_count)
    total_alloc = alloc_inbound + alloc_pip + alloc_panther + alloc_frosties

    # Cap by total assigned contacts: if owner already has >= total allocation, do not assign more.
    # This prevents over-assignment when Leads-based open counts undercount (e.g. pipeline stage or type mismatch).
    total_assigned_contacts = get_total_assigned_contacts_for_owner(client, owner_id)
    if total_alloc > 0 and total_assigned_contacts >= total_alloc:
        return {
            "owner_id": owner_id,
            "staff_id": staff_id,
            "staff_name": staff_name,
            "dry_run": dry_run,
            "planned_assignments": [],
            "planned_staff_updates": [],
            "summary": {"assignments_count": 0, "staff_updates_count": 0},
            "at_capacity": True,
            "total_assigned_contacts": total_assigned_contacts,
            "total_alloc": total_alloc,
        }

    availability = _str(_prop_value(staff_props, "availability"))
    is_available = availability != "Unavailable"

    def in_team(team_name: str) -> bool:
        return any(team_name in t or t in team_name for t in lead_teams_list)

    # Live mode: update staff open counts first (like N8N "Update amount of leads")
    if not dry_run and staff_id:
        client.patch_custom_object(
            HUBSPOT_STAFF_OBJECT_ID,
            staff_id,
            {
                "open_inbound_leads_n8n": open_inbound,
                "open_pip_leads_n8n": open_pip,
                "open_panther_leads": open_panther,
                "open_frosties_leads": open_frosties,
            },
        )

    # Order and config per type (matches N8N: Inbound, PIP, Frosties, Panther)
    type_config = [
        ("Inbound Lead Team", open_inbound, alloc_inbound, "inbound"),
        ("PIP Lead Team", open_pip, alloc_pip, "pip"),
        ("Frosties Lead Team", open_frosties, alloc_frosties, "frosties"),
        ("Panther Lead Team", open_panther, alloc_panther, "panther"),
    ]

    # Running open counts we'll update as we "assign" (for dry_run we only record; for live we PATCH and then update staff)
    running_open_inbound = open_inbound
    running_open_pip = open_pip
    running_open_frosties = open_frosties
    running_open_panther = open_panther

    # Cap total assignments by contact-based capacity (in case Leads-based open counts undercount)
    remaining_capacity = total_alloc - total_assigned_contacts

    for team_name, open_count, allocation, type_key in type_config:
        delta = allocation - open_count
        if delta <= 0 or not is_available or not in_team(team_name):
            continue
        # Do not assign more than remaining total capacity
        take_at_most = min(delta, remaining_capacity)
        if take_at_most <= 0:
            continue

        priorities = LEAD_PRIORITY_BY_TYPE.get(team_name, [])
        if not priorities:
            continue

        # Search unassigned contacts (no owner, no assign_lead, lead_priority in priorities, hs_lead_status = Open Lead)
        search_body = {
            "filterGroups": [{
                "filters": [
                    {"propertyName": "hubspot_owner_id", "operator": "NOT_HAS_PROPERTY"},
                    {"propertyName": "assign_lead", "operator": "NOT_HAS_PROPERTY"},
                    {"propertyName": "lead_priority", "operator": "IN", "values": priorities},
                    {"propertyName": "hs_lead_status", "operator": "EQ", "value": "Open Lead"},
                ],
            }],
            "sorts": [{"propertyName": "createdate", "direction": "ASCENDING"}],
            "limit": max(0, take_at_most),
            "properties": ["firstname", "lastname", "email", "hubspot_owner_id", "lead_priority", "hs_lead_status", "createdate"],
        }
        search_res = client.search_contacts(
            filter_groups=search_body["filterGroups"],
            properties=search_body["properties"],
            sorts=search_body["sorts"],
            limit=search_body["limit"],
        )
        candidates = search_res.get("results", [])
        # Only allocate each contact once per run (HubSpot API can lag, so same contact may appear unassigned for next owner)
        if assigned_this_run is not None:
            candidates = [c for c in candidates if c.get("id") is not None and str(c.get("id")) not in assigned_this_run]
        contacts_to_assign = candidates[:take_at_most]
        if assigned_this_run is not None:
            for c in contacts_to_assign:
                cid = c.get("id")
                if cid is not None:
                    assigned_this_run.add(str(cid))
        remaining_capacity -= len(contacts_to_assign)

        for c in contacts_to_assign:
            cid = c.get("id")
            c_props = c.get("properties", {})
            lead_priority = _prop_value(c_props, "lead_priority") or "—"
            if dry_run:
                planned_assignments.append({
                    "contact_id": cid,
                    "owner_id": owner_id,
                    "team": team_name,
                    "lead_priority": lead_priority,
                    "description": f"Would assign contact {cid} ({lead_priority}) to owner {owner_id} ({team_name})",
                })
            else:
                client.patch_contact(cid, {"hubspot_owner_id": owner_id, "assign_lead": "Yes"})

        num_assigned = len(contacts_to_assign)
        if num_assigned > 0:
            if type_key == "inbound":
                running_open_inbound += num_assigned
                staff_props_update = {"open_inbound_leads_n8n": running_open_inbound}
            elif type_key == "pip":
                running_open_pip += num_assigned
                staff_props_update = {"open_pip_leads_n8n": running_open_pip}
            elif type_key == "frosties":
                running_open_frosties += num_assigned
                staff_props_update = {"open_frosties_leads": running_open_frosties}
            else:  # panther
                running_open_panther += num_assigned
                staff_props_update = {"open_panther_leads": running_open_panther}

            if dry_run:
                planned_staff_updates.append({
                    "staff_id": staff_id,
                    "team": team_name,
                    "properties": staff_props_update,
                    "description": f"Would update Staff Member {staff_id}: {', '.join(f'{k}={v}' for k, v in staff_props_update.items())}",
                })
            else:
                client.patch_custom_object(HUBSPOT_STAFF_OBJECT_ID, staff_id, staff_props_update)

    return {
        "owner_id": owner_id,
        "staff_id": staff_id,
        "staff_name": staff_name,
        "dry_run": dry_run,
        "planned_assignments": planned_assignments,
        "planned_staff_updates": planned_staff_updates,
        "summary": {
            "assignments_count": len(planned_assignments),
            "staff_updates_count": len(planned_staff_updates),
        },
    }


def run_distribution(contact_id: str, dry_run: bool = True) -> dict:
    """
    Run distribution for the owner of the given contact.
    - contact_id: HubSpot contact ID (used to resolve hubspot_owner_id).
    - dry_run: if True, no PATCHes to HubSpot; return planned_assignments and planned_staff_updates.
    """
    client = HubSpotClient()
    contact = client.get_contact(contact_id, properties=["hubspot_owner_id"])
    owner_id = _prop_value(contact.get("properties", {}), "hubspot_owner_id")
    if not owner_id:
        return {
            "error": "Contact has no hubspot_owner_id",
            "planned_assignments": [],
            "planned_staff_updates": [],
            "summary": {"assignments_count": 0, "staff_updates_count": 0},
        }
    result = _run_distribution_for_owner(client, owner_id, dry_run=dry_run)
    result["contact_id"] = contact_id
    return result


def run_distribution_for_all_active(dry_run: bool = True) -> dict:
    """
    Run distribution for every currently active staff member.
    When dry_run=True: no contacts are assigned; returns planned actions.
    When dry_run=False: assigns contacts and updates staff open counts in HubSpot.
    Returns aggregated report: per-owner results and overall summary.
    """
    client = HubSpotClient()
    staff_result = client.search_custom_objects(
        HUBSPOT_STAFF_OBJECT_ID,
        filter_groups=[{"filters": [{"propertyName": "hubspot_owner_id", "operator": "HAS_PROPERTY"}]}],
        properties=["hubspot_owner_id", "availability", "name"],
        limit=100,
    )
    rows = staff_result.get("results", []) if isinstance(staff_result, dict) else []
    active = []
    for r in rows:
        props = r.get("properties") or {}
        availability = _str(_prop_value(props, "availability"))
        if availability == "Unavailable":
            continue
        raw = _prop_value(props, "hubspot_owner_id")
        owner_id = (str(raw).strip() if raw is not None else "") or None
        if not owner_id:
            continue
        name = _str(_prop_value(props, "name")) or None
        active.append({"owner_id": owner_id, "staff_name": name})

    results = []
    total_assignments = 0
    total_staff_updates = 0
    assigned_this_run: Set[str] = set()  # each contact allocated at most once per run (API lag safeguard)
    for item in active:
        one = _run_distribution_for_owner(
            client,
            item["owner_id"],
            dry_run=dry_run,
            staff_name=item.get("staff_name"),
            assigned_this_run=assigned_this_run,
        )
        results.append(one)
        total_assignments += len(one.get("planned_assignments", []))
        total_staff_updates += len(one.get("planned_staff_updates", []))

    return {
        "results": results,
        "summary": {
            "owners_processed": len(results),
            "total_assignments": total_assignments,
            "total_staff_updates": total_staff_updates,
        },
    }
