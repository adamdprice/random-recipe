"""HubSpot API client: owners, Staff and Lead Team custom objects."""
import requests
from typing import Any, Dict, List, Optional

from config import (
    HUBSPOT_ACCESS_TOKEN,
    HUBSPOT_STAFF_OBJECT_ID,
    HUBSPOT_LEAD_TEAM_OBJECT_ID,
)

BASE = "https://api.hubapi.com"


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {HUBSPOT_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }


def _get(url: str, params: Optional[Dict] = None) -> Dict[str, Any]:
    r = requests.get(url, headers=_headers(), params=params or {}, timeout=30)
    r.raise_for_status()
    return r.json()


def _post(url: str, json: Dict[str, Any]) -> Dict[str, Any]:
    r = requests.post(url, headers=_headers(), json=json, timeout=30)
    r.raise_for_status()
    return r.json()


def _patch(url: str, json: Dict[str, Any]) -> Dict[str, Any]:
    r = requests.patch(url, headers=_headers(), json=json, timeout=30)
    r.raise_for_status()
    return r.json()


def _delete(url: str) -> None:
    r = requests.delete(url, headers=_headers(), timeout=30)
    r.raise_for_status()


def list_owners() -> List[Dict[str, Any]]:
    """Return list of HubSpot owners (id, email, firstName, lastName)."""
    if not HUBSPOT_ACCESS_TOKEN:
        return []
    out: List[Dict[str, Any]] = []
    url = f"{BASE}/crm/v3/owners/"
    params: Dict[str, Any] = {"limit": 100}
    while True:
        data = _get(url, params)
        for r in (data.get("results") or []):
            out.append({
                "id": str(r.get("id", "")),
                "email": (r.get("email") or "").strip(),
                "firstName": (r.get("firstName") or "").strip(),
                "lastName": (r.get("lastName") or "").strip(),
            })
        after = (data.get("paging") or {}).get("next", {}).get("after")
        if not after:
            break
        params = {"limit": 100, "after": after}
    return out


def search_custom_objects(object_type_id: str, properties: List[str], filters: Optional[List[Dict]] = None) -> List[Dict[str, Any]]:
    """Search custom objects. object_type_id e.g. '2-194632537'."""
    if not HUBSPOT_ACCESS_TOKEN:
        return []
    url = f"{BASE}/crm/v3/objects/{object_type_id}/search"
    body: Dict[str, Any] = {"properties": properties}
    if filters:
        body["filterGroups"] = [{"filters": filters}]
    results: List[Dict[str, Any]] = []
    after = 0
    limit = 100
    while True:
        body["limit"] = limit
        body["after"] = after
        data = _post(url, body)
        for r in (data.get("results") or []):
            props = r.get("properties") or {}
            results.append({
                "id": r.get("id"),
                **{k: (props.get(k) or "") for k in properties},
            })
        after = data.get("after")
        if after is None:
            break
    return results


def get_staff_properties() -> List[str]:
    return [
        "hubspot_owner_id", "name", "availability", "lead_teams",
        "pause_leads", "call_minutes_last_120",
        "open_inbound_leads_n8n", "open_pip_leads_n8n",
        "open_panther_leads", "open_frosties_leads",
    ]


def get_all_staff() -> List[Dict[str, Any]]:
    """Fetch all Staff custom object records."""
    if not HUBSPOT_STAFF_OBJECT_ID:
        return []
    props = get_staff_properties()
    raw = search_custom_objects(HUBSPOT_STAFF_OBJECT_ID, props)
    return [normalize_staff(r) for r in raw]


def normalize_staff(r: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize staff record for API (id, name, availability, lead_teams, etc.)."""
    return {
        "id": r.get("id"),
        "hubspot_owner_id": (r.get("hubspot_owner_id") or "").strip(),
        "name": (r.get("name") or r.get("hubspot_owner_id") or "").strip() or None,
        "availability": (r.get("availability") or "Available").strip(),
        "lead_teams": (r.get("lead_teams") or "").strip(),
        "pause_leads": (r.get("pause_leads") or "").strip() or None,
        "call_minutes_last_120": _num(r.get("call_minutes_last_120")),
        "open_inbound_leads_n8n": _num(r.get("open_inbound_leads_n8n")),
        "open_pip_leads_n8n": _num(r.get("open_pip_leads_n8n")),
        "open_panther_leads": _num(r.get("open_panther_leads")),
        "open_frosties_leads": _num(r.get("open_frosties_leads")),
        "on_holiday_today": False,  # filled by app layer from holidays
    }


def _num(v: Any) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def get_staff_by_id(staff_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a single Staff record by id."""
    if not HUBSPOT_ACCESS_TOKEN or not HUBSPOT_STAFF_OBJECT_ID:
        return None
    url = f"{BASE}/crm/v3/objects/{HUBSPOT_STAFF_OBJECT_ID}/{staff_id}"
    params = {"properties": ",".join(get_staff_properties())}
    try:
        r = _get(url, params)
        props = r.get("properties") or {}
        rec = {"id": r.get("id"), **{k: (props.get(k) or "") for k in get_staff_properties()}}
        return normalize_staff(rec)
    except Exception:
        return None


def create_custom_object(object_type_id: str, properties: Dict[str, str]) -> Dict[str, Any]:
    """Create one custom object. Returns created object with id."""
    url = f"{BASE}/crm/v3/objects/{object_type_id}"
    body = {"properties": {k: str(v) for k, v in properties.items()}}
    return _post(url, body)


def patch_custom_object(object_type_id: str, object_id: str, properties: Dict[str, str]) -> Dict[str, Any]:
    """Patch custom object properties."""
    url = f"{BASE}/crm/v3/objects/{object_type_id}/{object_id}"
    body = {"properties": {k: str(v) for k, v in properties.items()}}
    return _patch(url, body)


def get_lead_team_properties() -> List[str]:
    return ["name", "unallocated", "max_leads"]


def get_all_lead_teams() -> List[Dict[str, Any]]:
    """Fetch all Lead Team custom object records."""
    if not HUBSPOT_LEAD_TEAM_OBJECT_ID:
        return []
    props = get_lead_team_properties()
    raw = search_custom_objects(HUBSPOT_LEAD_TEAM_OBJECT_ID, props)
    return [
        {
            "id": r.get("id"),
            "name": (r.get("name") or "").strip() or None,
            "unallocated": _num(r.get("unallocated")),
            "max_leads": _num(r.get("max_leads")),
        }
        for r in raw
    ]


def patch_lead_team(team_id: str, max_leads: int) -> Dict[str, Any]:
    """Update lead team max_leads."""
    return patch_custom_object(HUBSPOT_LEAD_TEAM_OBJECT_ID, team_id, {"max_leads": str(max_leads)})


def test_connection() -> bool:
    """Verify HubSpot token works (e.g. list owners)."""
    if not HUBSPOT_ACCESS_TOKEN:
        return False
    try:
        list_owners()
        return True
    except Exception:
        return False
