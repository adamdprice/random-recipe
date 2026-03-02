#!/usr/bin/env python3
"""Quick diagnostic: why might distribution assign 0 contacts?"""
import os
import sys

if os.path.exists(".env"):
    try:
        from dotenv import load_dotenv
        load_dotenv(".env")
    except Exception:
        pass

from config import LEAD_PRIORITY_BY_TYPE
from hubspot_client import HubSpotClient

def main():
    token = os.getenv("HUBSPOT_ACCESS_TOKEN", "")
    if not token:
        print("HUBSPOT_ACCESS_TOKEN not set")
        sys.exit(1)
    client = HubSpotClient()

    # Count unallocated contacts WITH hs_lead_status = "Open Lead" (what we filter on)
    for team_name, priorities in LEAD_PRIORITY_BY_TYPE.items():
        r = client.search_contacts(
            filter_groups=[{
                "filters": [
                    {"propertyName": "hubspot_owner_id", "operator": "NOT_HAS_PROPERTY"},
                    {"propertyName": "assign_lead", "operator": "NOT_HAS_PROPERTY"},
                    {"propertyName": "lead_priority", "operator": "IN", "values": priorities},
                    {"propertyName": "hs_lead_status", "operator": "EQ", "value": "Open Lead"},
                ],
            }],
            properties=["lead_priority", "hs_lead_status"],
            limit=1,
        )
        total = r.get("total", 0) or 0
        print(f"Unallocated + Open Lead + {team_name} (priorities {priorities}): total = {total}")

    # Same but WITHOUT hs_lead_status filter - to see if pool exists without that filter
    print("\nWithout hs_lead_status filter (Inbound only):")
    r2 = client.search_contacts(
        filter_groups=[{
            "filters": [
                {"propertyName": "hubspot_owner_id", "operator": "NOT_HAS_PROPERTY"},
                {"propertyName": "assign_lead", "operator": "NOT_HAS_PROPERTY"},
                {"propertyName": "lead_priority", "operator": "IN", "values": ["High", "High (Applied Before)", "High (Callback)"]},
            ],
        }],
        properties=["lead_priority", "hs_lead_status"],
        limit=5,
    )
    total2 = r2.get("total", 0) or 0
    print(f"  Unallocated Inbound (any status): total = {total2}")
    for c in (r2.get("results") or [])[:3]:
        props = c.get("properties") or {}
        hs = props.get("hs_lead_status") or props.get("hs_lead_status", {}).get("value")
        print(f"    Contact id={c.get('id')} lead_priority={props.get('lead_priority')} hs_lead_status={hs}")

def one_owner_debug():
    """Run distribution for first active owner only and print why 0 or N assignments."""
    import math
    from distribution_engine import (
        _run_distribution_for_owner,
        get_total_assigned_contacts_for_owner,
        get_open_lead_counts_for_owner,
        _prop_value,
        _str,
        _num,
    )
    from config import HUBSPOT_STAFF_OBJECT_ID
    client = HubSpotClient()
    # Get first active owner from staff
    # Prefer first *available* owner so we can see assignments (first in list may be Unavailable)
    staff_result = client.search_custom_objects(
        HUBSPOT_STAFF_OBJECT_ID,
        filter_groups=[{"filters": [{"propertyName": "hubspot_owner_id", "operator": "HAS_PROPERTY"}]}],
        properties=["hubspot_owner_id", "availability", "name", "lead_teams", "max_inbound_leads", "max_pip_leads"],
        limit=50,
    )
    rows = staff_result.get("results", []) or []
    if not rows:
        print("No staff found")
        return
    # Pick first available; fallback to first row
    r = None
    for row in rows:
        if _str(_prop_value(row.get("properties") or {}, "availability")) != "Unavailable":
            r = row
            break
    if r is None:
        r = rows[0]
        print("(All staff Unavailable; showing first owner anyway.)")
    props = r.get("properties") or {}
    raw = _prop_value(props, "hubspot_owner_id")
    owner_id = (str(raw).strip() if raw else "") or None
    if not owner_id:
        print("No owner_id on first staff")
        return
    name = _str(_prop_value(props, "name"))
    print(f"First owner: {owner_id} ({name})")
    total_assigned = get_total_assigned_contacts_for_owner(client, owner_id)
    print(f"  total_assigned_contacts (Contacts API): {total_assigned}")
    lead_teams = _str(_prop_value(props, "lead_teams"))
    lead_teams_list = [t.strip() for t in lead_teams.split(";") if t.strip()]
    team_count = len(lead_teams_list) or 1
    print(f"  lead_teams: {repr(lead_teams)} -> team_count={team_count}")
    max_inbound = _num(_prop_value(props, "max_inbound_leads"))
    max_pip = _num(_prop_value(props, "max_pip_leads"))
    print(f"  max_inbound_leads: {max_inbound} max_pip_leads: {max_pip}")
    # Open counts from Leads object (what distribution_engine uses for delta)
    counts = get_open_lead_counts_for_owner(client, owner_id)
    open_inbound = counts["open_inbound_leads_n8n"]
    open_pip = counts["open_pip_leads_n8n"]
    alloc_inbound = (int(math.ceil(max_inbound / team_count)) if team_count else 0)
    alloc_pip = (int(math.ceil(max_pip / team_count)) if team_count else 0)
    delta_inbound = alloc_inbound - open_inbound
    delta_pip = alloc_pip - open_pip
    print(f"  Open counts (Leads object): inbound={open_inbound} pip={open_pip}")
    print(f"  Allocation (per team): inbound={alloc_inbound} pip={alloc_pip}")
    print(f"  Delta (alloc - open): inbound={delta_inbound} pip={delta_pip} -> assign only if delta > 0")
    availability = _str(_prop_value(props, "availability"))
    print(f"  availability: {repr(availability)} -> is_available: {availability != 'Unavailable'}")
    # Direct contact search (same as engine) for Inbound to see if we get candidates
    from config import LEAD_PRIORITY_BY_TYPE
    priorities = LEAD_PRIORITY_BY_TYPE.get("Inbound Lead Team", [])
    direct = client.search_contacts(
        filter_groups=[{
            "filters": [
                {"propertyName": "hubspot_owner_id", "operator": "NOT_HAS_PROPERTY"},
                {"propertyName": "assign_lead", "operator": "NOT_HAS_PROPERTY"},
                {"propertyName": "lead_priority", "operator": "IN", "values": priorities},
                {"propertyName": "hs_lead_status", "operator": "EQ", "value": "Open Lead"},
            ],
        }],
        properties=["lead_priority", "hs_lead_status"],
        limit=5,
    )
    direct_results = direct.get("results", []) or []
    print(f"  Direct search unallocated Inbound Open Lead: {len(direct_results)} (limit 5)")
    result = _run_distribution_for_owner(client, owner_id, dry_run=True, staff_name=name, assigned_this_run=set())
    print(f"  at_capacity: {result.get('at_capacity')} total_alloc: {result.get('total_alloc')}")
    print(f"  planned_assignments: {len(result.get('planned_assignments', []))}")
    if result.get("error"):
        print(f"  error: {result['error']}")


def debug_staff_by_name(search_name: str):
    """Run same diagnostic for a staff member by name (e.g. 'Aman Bansal')."""
    import math
    from distribution_engine import (
        _run_distribution_for_owner,
        get_total_assigned_contacts_for_owner,
        get_open_lead_counts_for_owner,
        _prop_value,
        _str,
        _num,
    )
    from config import HUBSPOT_STAFF_OBJECT_ID, LEAD_PRIORITY_BY_TYPE
    client = HubSpotClient()
    staff_result = client.search_custom_objects(
        HUBSPOT_STAFF_OBJECT_ID,
        filter_groups=[{"filters": [{"propertyName": "hubspot_owner_id", "operator": "HAS_PROPERTY"}]}],
        properties=["hubspot_owner_id", "availability", "name", "lead_teams", "max_inbound_leads", "max_pip_leads", "max_panther_leads", "max_frosties_leads"],
        limit=100,
    )
    rows = staff_result.get("results", []) or []
    search_lower = search_name.strip().lower()
    r = None
    for row in rows:
        props = row.get("properties") or {}
        name_val = _str(_prop_value(props, "name"))
        if search_lower in name_val.lower() or name_val.lower() in search_lower:
            r = row
            break
    if r is None:
        print(f"No staff found matching '{search_name}' (checked {len(rows)} staff)")
        return
    props = r.get("properties") or {}
    raw = _prop_value(props, "hubspot_owner_id")
    owner_id = (str(raw).strip() if raw else "") or None
    if not owner_id:
        print(f"Staff '{_str(_prop_value(props, 'name'))}' has no hubspot_owner_id")
        return
    name = _str(_prop_value(props, "name"))
    print(f"Staff: {name} (owner_id={owner_id})")
    total_assigned = get_total_assigned_contacts_for_owner(client, owner_id)
    print(f"  total_assigned_contacts (Contacts API): {total_assigned}")
    lead_teams = _str(_prop_value(props, "lead_teams"))
    lead_teams_list = [t.strip() for t in lead_teams.split(";") if t.strip()]
    team_count = len(lead_teams_list) or 1
    print(f"  lead_teams: {repr(lead_teams)} -> team_count={team_count}")
    max_inbound = _num(_prop_value(props, "max_inbound_leads"))
    max_pip = _num(_prop_value(props, "max_pip_leads"))
    max_panther = _num(_prop_value(props, "max_panther_leads"))
    max_frosties = _num(_prop_value(props, "max_frosties_leads"))
    print(f"  max_*_leads: inbound={max_inbound} pip={max_pip} panther={max_panther} frosties={max_frosties}")
    counts = get_open_lead_counts_for_owner(client, owner_id)
    open_inbound = counts["open_inbound_leads_n8n"]
    open_pip = counts["open_pip_leads_n8n"]
    open_panther = counts["open_panther_leads"]
    open_frosties = counts["open_frosties_leads"]
    alloc_inbound = (int(math.ceil(max_inbound / team_count)) if team_count else 0)
    alloc_pip = (int(math.ceil(max_pip / team_count)) if team_count else 0)
    alloc_panther = (int(math.ceil(max_panther / team_count)) if team_count else 0)
    alloc_frosties = (int(math.ceil(max_frosties / team_count)) if team_count else 0)
    total_alloc = alloc_inbound + alloc_pip + alloc_panther + alloc_frosties
    delta_inbound = alloc_inbound - open_inbound
    delta_pip = alloc_pip - open_pip
    print(f"  Open counts (Leads): inbound={open_inbound} pip={open_pip} panther={open_panther} frosties={open_frosties}")
    print(f"  Allocation (per team): inbound={alloc_inbound} pip={alloc_pip} panther={alloc_panther} frosties={alloc_frosties} -> total_alloc={total_alloc}")
    print(f"  Delta (alloc - open): inbound={delta_inbound} pip={delta_pip} (assign if delta > 0)")
    availability = _str(_prop_value(props, "availability"))
    is_available = availability != "Unavailable"
    print(f"  availability: {repr(availability)} -> is_available: {is_available}")
    print(f"  at_capacity (assigned >= total_alloc)? {total_assigned >= total_alloc if total_alloc else 'N/A'} ({total_assigned} >= {total_alloc})")
    result = _run_distribution_for_owner(client, owner_id, dry_run=True, staff_name=name, assigned_this_run=set())
    planned = result.get("planned_assignments", [])
    print(f"  planned_assignments: {len(planned)}")
    if result.get("error"):
        print(f"  error: {result['error']}")
    if planned:
        for p in planned[:5]:
            print(f"    - {p.get('description', p)}")
        if len(planned) > 5:
            print(f"    ... and {len(planned) - 5} more")


if __name__ == "__main__":
    main()
    print("\n--- One-owner debug ---")
    one_owner_debug()
    if len(sys.argv) > 1:
        print("\n--- Staff by name ---")
        debug_staff_by_name(" ".join(sys.argv[1:]))
