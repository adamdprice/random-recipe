"""Dry-run distribution: compute planned assignments and staff updates (no HubSpot writes)."""
from typing import Any, Dict, List

import hubspot_client as hc
from config import HUBSPOT_STAFF_OBJECT_ID
from holidays import is_on_holiday_today


def run_dry_run() -> Dict[str, Any]:
    """
    Run a test distribution: for each active staff (available, not on holiday),
    compute what would be assigned and what staff props would be updated.
    Returns { summary: { owners_processed, total_assignments, total_staff_updates }, results: [ per-owner ] }.
    """
    staff_list = hc.get_all_staff() if HUBSPOT_STAFF_OBJECT_ID else []
    # Mark holiday
    for s in staff_list:
        s["on_holiday_today"] = is_on_holiday_today(str(s.get("id") or ""))

    active = [
        s for s in staff_list
        if (s.get("availability") or "").lower() != "unavailable"
        and not s.get("on_holiday_today")
    ]

    total_assignments = 0
    total_staff_updates = 0
    results: List[Dict[str, Any]] = []

    for s in active:
        owner_id = s.get("hubspot_owner_id") or ""
        name = s.get("name") or owner_id or ("Staff " + str(s.get("id")))
        planned_assignments: List[Dict[str, Any]] = []
        planned_staff_updates: List[Dict[str, Any]] = []
        # Placeholder: no real contact search; just structure for UI
        results.append({
            "owner_id": owner_id,
            "staff_name": name,
            "staff_id": s.get("id"),
            "planned_assignments": planned_assignments,
            "planned_staff_updates": planned_staff_updates,
            "error": None,
        })
        total_assignments += len(planned_assignments)
        total_staff_updates += len(planned_staff_updates)

    return {
        "summary": {
            "owners_processed": len(results),
            "total_assignments": total_assignments,
            "total_staff_updates": total_staff_updates,
        },
        "results": results,
    }
