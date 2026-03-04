"""
Re-Distribute Leads: show unqualified leads by disqualification reason (Volume, No Response, Maybe)
and allow re-opening them (unassign contact, set Open Lead, move lead to new stage, clear reason).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

# Max time (seconds) to spend in HubSpot search loop so we respond before frontend 25s timeout
REDISTRIBUTE_COUNTS_DEADLINE_SECONDS = 22

from hubspot_client import HubSpotClient
from config import (
    REDISTRIBUTE_LEAD_PIPELINE_ID,
    REDISTRIBUTE_UNQUALIFIED_STAGE_ID,
    REDISTRIBUTE_NEW_STAGE_ID,
    REDISTRIBUTE_DISQUALIFICATION_PROPERTY,
    REDISTRIBUTE_DATE_ENTERED_PROPERTY,
    REDISTRIBUTE_REASONS,
    REDISTRIBUTE_OPEN_LEAD_STATUS,
    REDISTRIBUTE_STAGING_NAME_CONTAINS,
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
) -> dict:
    """
    Return counts of unqualified leads per reason (Volume, No Response, Maybe (wants to think)).
    Only leads in pipeline REDISTRIBUTE_LEAD_PIPELINE_ID, stage REDISTRIBUTE_UNQUALIFIED_STAGE_ID.
    If last_days is set, filter by REDISTRIBUTE_DATE_ENTERED_PROPERTY >= (now - last_days).
    If REDISTRIBUTE_STAGING_NAME_CONTAINS is set, only leads whose name contains that string.
    Returns: { "counts": { "Volume": n, "No Response": n, "Maybe (wants to think)": n }, "error": optional }
    """
    filters = [
        {"propertyName": "hs_pipeline", "operator": "EQ", "value": REDISTRIBUTE_LEAD_PIPELINE_ID},
        {"propertyName": "hs_pipeline_stage", "operator": "EQ", "value": REDISTRIBUTE_UNQUALIFIED_STAGE_ID},
        {"propertyName": REDISTRIBUTE_DISQUALIFICATION_PROPERTY, "operator": "IN", "value": REDISTRIBUTE_REASONS},
    ]
    if last_days is not None and last_days > 0:
        since_ms = int((datetime.now(timezone.utc) - timedelta(days=last_days)).timestamp() * 1000)
        filters.append({
            "propertyName": REDISTRIBUTE_DATE_ENTERED_PROPERTY,
            "operator": "GTE",
            "value": str(since_ms),
        })
    if REDISTRIBUTE_STAGING_NAME_CONTAINS:
        filters.append({
            "propertyName": REDISTRIBUTE_LEAD_NAME_PROPERTY,
            "operator": "CONTAINS_TOKEN",
            "value": REDISTRIBUTE_STAGING_NAME_CONTAINS,
        })
    filter_groups = [{"filters": filters}]
    properties = [REDISTRIBUTE_DISQUALIFICATION_PROPERTY]
    if REDISTRIBUTE_STAGING_NAME_CONTAINS:
        properties.append(REDISTRIBUTE_LEAD_NAME_PROPERTY)
    counts = {r: 0 for r in REDISTRIBUTE_REASONS}
    # Skip HubSpot call if pipeline/stage are still placeholders (avoids slow or invalid API calls)
    if REDISTRIBUTE_LEAD_PIPELINE_ID in ("lead-pipeline-id", "") or REDISTRIBUTE_UNQUALIFIED_STAGE_ID in ("unqualified-stage-id", ""):
        return {"counts": counts, "error": "Configure REDISTRIBUTE_LEAD_PIPELINE_ID and REDISTRIBUTE_UNQUALIFIED_STAGE_ID in environment."}
    try:
        all_results = []
        after = None
        max_pages = 20  # cap at 2000 leads to avoid infinite pagination
        deadline = time.monotonic() + REDISTRIBUTE_COUNTS_DEADLINE_SECONDS
        for _ in range(max_pages):
            if time.monotonic() >= deadline:
                _log.warning("redistribute counts: hit time limit, returning partial counts")
                break
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
        return {"counts": counts}
    except Exception as e:
        _log.exception("redistribute counts failed")
        return {"counts": counts, "error": str(e)}


def execute_redistribute(
    client: HubSpotClient,
    reason: str,
    last_days: Optional[int] = None,
) -> dict:
    """
    For all unqualified leads with the given reason (same filters as counts), re-distribute:
    - Contact: clear hubspot_owner_id, set hs_lead_status = Open Lead, clear assign_lead
    - Lead: move to REDISTRIBUTE_NEW_STAGE_ID, clear hs_lead_disqualification_reason
    Returns: { "redistributed": n, "errors": [...], "error": optional }
    """
    if reason not in REDISTRIBUTE_REASONS:
        return {"redistributed": 0, "errors": [], "error": f"Invalid reason: {reason}"}
    filters = [
        {"propertyName": "hs_pipeline", "operator": "EQ", "value": REDISTRIBUTE_LEAD_PIPELINE_ID},
        {"propertyName": "hs_pipeline_stage", "operator": "EQ", "value": REDISTRIBUTE_UNQUALIFIED_STAGE_ID},
        {"propertyName": REDISTRIBUTE_DISQUALIFICATION_PROPERTY, "operator": "EQ", "value": reason},
    ]
    if last_days is not None and last_days > 0:
        since_ms = int((datetime.now(timezone.utc) - timedelta(days=last_days)).timestamp() * 1000)
        filters.append({
            "propertyName": REDISTRIBUTE_DATE_ENTERED_PROPERTY,
            "operator": "GTE",
            "value": str(since_ms),
        })
    if REDISTRIBUTE_STAGING_NAME_CONTAINS:
        filters.append({
            "propertyName": REDISTRIBUTE_LEAD_NAME_PROPERTY,
            "operator": "CONTAINS_TOKEN",
            "value": REDISTRIBUTE_STAGING_NAME_CONTAINS,
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
        return {"redistributed": 0, "errors": [], "error": str(e)}
    if not all_lead_ids:
        return {"redistributed": 0, "errors": []}
    assoc = client.get_lead_to_contact_associations_batch(all_lead_ids)
    errors = []
    redistributed = 0
    for lead_id in all_lead_ids:
        contact_ids = assoc.get(lead_id) or []
        contact_id = contact_ids[0] if contact_ids else None
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
        except Exception as e:
            errors.append({"lead_id": lead_id, "message": str(e)})
    return {"redistributed": redistributed, "errors": errors}
