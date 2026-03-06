"""
Re-Distribute Leads: show unqualified leads by disqualification reason (Volume, No Response, Maybe)
and allow re-opening them (unassign contact, set Open Lead, move lead to new stage, clear reason).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from hubspot_client import HubSpotClient
from config import (
    REDISTRIBUTE_LEAD_PIPELINE_ID,
    REDISTRIBUTE_UNQUALIFIED_STAGE_ID,
    REDISTRIBUTE_NEW_STAGE_ID,
    REDISTRIBUTE_DISQUALIFICATION_PROPERTY,
    REDISTRIBUTE_DATE_ENTERED_PROPERTY,
    REDISTRIBUTE_REASONS,
    REDISTRIBUTE_OPEN_LEAD_STATUS,
    REDISTRIBUTE_LEAD_NAME_PROPERTY,
)

_log = logging.getLogger(__name__)


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


def get_redistribute_counts(
    client: HubSpotClient,
    last_days: Optional[int] = None,
    lead_type: Optional[str] = None,
) -> dict:
    """
    Return counts of unqualified leads per reason (Volume, No Response, Maybe (wants to think)).
    Only leads in pipeline REDISTRIBUTE_LEAD_PIPELINE_ID, stage REDISTRIBUTE_UNQUALIFIED_STAGE_ID.
    If last_days is set, filter by REDISTRIBUTE_DATE_ENTERED_PROPERTY >= (now - last_days).
    If lead_type is set (e.g. Inbound Lead, PIP Lead), filter by hs_lead_type.
    Returns: { "counts": { "Volume": n, ... }, "error": optional }
    """
    from config import REDISTRIBUTE_LEAD_TYPES
    filters = [
        {"propertyName": "hs_pipeline", "operator": "EQ", "value": REDISTRIBUTE_LEAD_PIPELINE_ID},
        {"propertyName": "hs_pipeline_stage", "operator": "EQ", "value": REDISTRIBUTE_UNQUALIFIED_STAGE_ID},
        {"propertyName": REDISTRIBUTE_DISQUALIFICATION_PROPERTY, "operator": "IN", "values": REDISTRIBUTE_REASONS},
    ]
    if lead_type and lead_type in REDISTRIBUTE_LEAD_TYPES:
        filters.append({"propertyName": "hs_lead_type", "operator": "EQ", "value": lead_type})
    if last_days is not None and last_days > 0:
        since_ms = int((datetime.now(timezone.utc) - timedelta(days=last_days)).timestamp() * 1000)
        filters.append({
            "propertyName": REDISTRIBUTE_DATE_ENTERED_PROPERTY,
            "operator": "GTE",
            "value": str(since_ms),
        })
    filter_groups = [{"filters": filters}]
    properties = [REDISTRIBUTE_DISQUALIFICATION_PROPERTY, "hs_lead_type"]
    counts = {r: 0 for r in REDISTRIBUTE_REASONS}
    try:
        all_results = []
        after = None
        max_pages = 20  # cap at 2000 leads to avoid infinite pagination
        for _ in range(max_pages):
            res = client.search_leads(
                filter_groups=filter_groups,
                properties=properties,
                limit=100,
                after=after,
            )
            results = res.get("results", [])
            all_results.extend(results)
            after = (res.get("paging") or {}).get("next", {}).get("after")
            if not after or len(results) < 100:
                break
        for lead in all_results:
            props = lead.get("properties") or {}
            reason = _str(_prop_value(props, REDISTRIBUTE_DISQUALIFICATION_PROPERTY))
            if reason in counts:
                counts[reason] += 1
        total = sum(counts.values())
        if last_days is not None and last_days > 0 and total == 0:
            # Date filter returned nothing – date may not be set on leads; retry without date filter
            filters_no_date = [f for f in filters if f.get("propertyName") != REDISTRIBUTE_DATE_ENTERED_PROPERTY]
            filter_groups_fallback = [{"filters": filters_no_date}]
            all_results = []
            after = None
            for _ in range(max_pages):
                res = client.search_leads(
                    filter_groups=filter_groups_fallback,
                    properties=properties,
                    limit=100,
                    after=after,
                )
                results = res.get("results", [])
                all_results.extend(results)
                after = (res.get("paging") or {}).get("next", {}).get("after")
                if not after or len(results) < 100:
                    break
            counts = {r: 0 for r in REDISTRIBUTE_REASONS}
            for lead in all_results:
                props = lead.get("properties") or {}
                reason = _str(_prop_value(props, REDISTRIBUTE_DISQUALIFICATION_PROPERTY))
                if reason in counts:
                    counts[reason] += 1
            return {"counts": counts, "date_filter_not_applied": True, "message": "Date entered isn't set for these leads; showing all-time counts."}
        return {"counts": counts}
    except Exception as e:
        _log.exception("redistribute counts failed")
        return {"counts": counts, "error": str(e)}


def execute_redistribute(
    client: HubSpotClient,
    reason: str,
    last_days: Optional[int] = None,
    lead_type: Optional[str] = None,
) -> dict:
    """
    For all unqualified leads with the given reason (same filters as counts), re-distribute:
    - Contact: clear hubspot_owner_id, set hs_lead_status = Open Lead, clear assign_lead
    - Lead: move to REDISTRIBUTE_NEW_STAGE_ID, clear hs_lead_disqualification_reason
    If lead_type is set, only leads with that hs_lead_type are included.
    Returns: { "redistributed": n, "errors": [...], "error": optional }
    """
    from config import REDISTRIBUTE_LEAD_TYPES
    if reason not in REDISTRIBUTE_REASONS:
        return {"redistributed": 0, "errors": [], "lead_ids": [], "error": f"Invalid reason: {reason}"}
    filters = [
        {"propertyName": "hs_pipeline", "operator": "EQ", "value": REDISTRIBUTE_LEAD_PIPELINE_ID},
        {"propertyName": "hs_pipeline_stage", "operator": "EQ", "value": REDISTRIBUTE_UNQUALIFIED_STAGE_ID},
        {"propertyName": REDISTRIBUTE_DISQUALIFICATION_PROPERTY, "operator": "EQ", "value": reason},
    ]
    if lead_type and lead_type in REDISTRIBUTE_LEAD_TYPES:
        filters.append({"propertyName": "hs_lead_type", "operator": "EQ", "value": lead_type})
    if last_days is not None and last_days > 0:
        since_ms = int((datetime.now(timezone.utc) - timedelta(days=last_days)).timestamp() * 1000)
        filters.append({
            "propertyName": REDISTRIBUTE_DATE_ENTERED_PROPERTY,
            "operator": "GTE",
            "value": str(since_ms),
        })
    filter_groups = [{"filters": filters}]
    properties = ["hs_object_id"]
    all_lead_ids = []
    try:
        after = None
        while True:
            res = client.search_leads(
                filter_groups=filter_groups,
                properties=properties,
                limit=100,
                after=after,
            )
            results = res.get("results", [])
            for lead in results:
                lid = lead.get("id")
                if lid:
                    all_lead_ids.append(str(lid))
            after = (res.get("paging") or {}).get("next", {}).get("after")
            if not after or len(results) < 100:
                break
    except Exception as e:
        _log.exception("redistribute fetch leads failed")
        return {"redistributed": 0, "errors": [], "lead_ids": [], "error": str(e)}
    if not all_lead_ids:
        return {"redistributed": 0, "errors": [], "lead_ids": []}
    assoc = client.get_lead_to_contact_associations_batch(all_lead_ids)
    errors = []
    redistributed = 0
    lead_ids_done: list[str] = []
    _TARGET_CID = "691929662686"
    for lead_id in all_lead_ids:
        contact_ids = assoc.get(lead_id) or []
        contact_id = contact_ids[0] if contact_ids else None
        # #region agent log
        try:
            import json
            with open("/Users/tga/Cursor/.cursor/debug-f32963.log", "a") as _f:
                _f.write(json.dumps({"sessionId": "f32963", "location": "redistribute.py:execute_redistribute", "message": "live path per-lead", "data": {"lead_id": lead_id, "contact_id": contact_id, "num_contacts": len(contact_ids), "target_in_list": _TARGET_CID in contact_ids, "using_target": contact_id == _TARGET_CID}, "hypothesisId": "A", "timestamp": __import__("time").time() * 1000}) + "\n")
        except Exception:
            pass
        # #endregion
        try:
            if contact_id:
                client.patch_contact(contact_id, {
                    "hubspot_owner_id": "",
                    "hs_lead_status": REDISTRIBUTE_OPEN_LEAD_STATUS,
                    "assign_lead": "",
                })
            client.patch_lead(lead_id, {
                "hs_pipeline": REDISTRIBUTE_LEAD_PIPELINE_ID,
                "hs_pipeline_stage": REDISTRIBUTE_NEW_STAGE_ID,
                REDISTRIBUTE_DISQUALIFICATION_PROPERTY: "",
            })
            redistributed += 1
            lead_ids_done.append(lead_id)
        except Exception as e:
            errors.append({"lead_id": lead_id, "message": str(e)})
    return {"redistributed": redistributed, "errors": errors, "lead_ids": lead_ids_done}


def lookup_lead_for_redistribute(client: HubSpotClient, lead_id: str) -> dict:
    """
    Fetch a lead by ID for single-lead re-distribute confirmation.
    Returns { "lead_id": str, "lead_name": str, "contact_id": str | None, "error": str | None }.
    """
    lead_id = (lead_id or "").strip()
    if not lead_id:
        return {"lead_id": "", "lead_name": "", "contact_id": None, "error": "Lead ID is required"}
    try:
        lead = client.get_lead(lead_id, properties=[REDISTRIBUTE_LEAD_NAME_PROPERTY, "hs_pipeline", "hs_pipeline_stage"])
    except Exception as e:
        _log.exception("lookup_lead_for_redistribute get_lead failed")
        return {"lead_id": lead_id, "lead_name": "", "contact_id": None, "error": str(e)}
    props = lead.get("properties") or {}
    name = _str(_prop_value(props, REDISTRIBUTE_LEAD_NAME_PROPERTY)) or f"Lead {lead_id}"
    assoc = client.get_lead_to_contact_associations_batch([lead_id])
    contact_ids = assoc.get(lead_id) or []
    contact_id = str(contact_ids[0]) if contact_ids else None
    return {"lead_id": lead_id, "lead_name": name, "contact_id": contact_id, "error": None}


def execute_single_lead_redistribute(client: HubSpotClient, lead_id: str) -> dict:
    """
    Re-distribute a single lead: clear contact owner + set status, move lead to new stage, clear reason.
    Returns { "success": bool, "error": str | None, "contact_updated": bool, "lead_updated": bool }.
    """
    lead_id = (lead_id or "").strip()
    if not lead_id:
        return {"success": False, "error": "Lead ID is required", "contact_updated": False, "lead_updated": False}
    try:
        assoc = client.get_lead_to_contact_associations_batch([lead_id])
        contact_ids = assoc.get(lead_id) or []
        contact_id = str(contact_ids[0]) if contact_ids else None
        if contact_id:
            client.patch_contact(contact_id, {
                "hubspot_owner_id": "",
                "hs_lead_status": REDISTRIBUTE_OPEN_LEAD_STATUS,
                "assign_lead": "",
            })
        client.patch_lead(lead_id, {
            "hs_pipeline": REDISTRIBUTE_LEAD_PIPELINE_ID,
            "hs_pipeline_stage": REDISTRIBUTE_NEW_STAGE_ID,
            REDISTRIBUTE_DISQUALIFICATION_PROPERTY: "",
        })
        return {"success": True, "error": None, "contact_updated": bool(contact_id), "lead_updated": True}
    except Exception as e:
        _log.exception("execute_single_lead_redistribute failed")
        return {"success": False, "error": str(e), "contact_updated": False, "lead_updated": False}


def execute_redistribute_batch(
    client: HubSpotClient,
    lead_rows: list[dict],
) -> dict:
    """
    Re-distribute a pre-resolved list of leads (e.g. from DB cache).
    Each item: { "lead_id": str, "contact_id": str | None }.
    Same contact/lead patches as execute_redistribute.
    Returns { "redistributed": n, "errors": [...], "lead_ids": [ids that were successfully re-distributed] }.
    """
    errors = []
    redistributed = 0
    lead_ids_done: list[str] = []
    _TARGET_CID = "691929662686"
    for row in lead_rows:
        lead_id = (row.get("lead_id") or "").strip()
        contact_id = (row.get("contact_id") or "").strip() or None
        if not lead_id:
            continue
        # #region agent log
        try:
            import json
            with open("/Users/tga/Cursor/.cursor/debug-f32963.log", "a") as _f:
                _f.write(json.dumps({"sessionId": "f32963", "location": "redistribute.py:execute_redistribute_batch", "message": "cache path per-row", "data": {"lead_id": lead_id, "contact_id": contact_id, "is_target_contact": contact_id == _TARGET_CID}, "hypothesisId": "B", "timestamp": __import__("time").time() * 1000}) + "\n")
        except Exception:
            pass
        # #endregion
        try:
            if contact_id:
                client.patch_contact(contact_id, {
                    "hubspot_owner_id": "",
                    "hs_lead_status": REDISTRIBUTE_OPEN_LEAD_STATUS,
                    "assign_lead": "",
                })
            client.patch_lead(lead_id, {
                "hs_pipeline": REDISTRIBUTE_LEAD_PIPELINE_ID,
                "hs_pipeline_stage": REDISTRIBUTE_NEW_STAGE_ID,
                REDISTRIBUTE_DISQUALIFICATION_PROPERTY: "",
            })
            redistributed += 1
            lead_ids_done.append(lead_id)
        except Exception as e:
            errors.append({"lead_id": lead_id, "message": str(e)})
    return {"redistributed": redistributed, "errors": errors, "lead_ids": lead_ids_done}
