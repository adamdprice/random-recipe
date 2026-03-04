"""
Re-distribute unqualified leads cache in PostgreSQL.
Stores lead_id, contact_id, lead_type, disqualification_reason, date_entered_unqualified_ms
so counts and execute can run from DB (refreshed every 2 hours) instead of hitting HubSpot search.
Uses DATABASE_URL; when unset, cache is skipped and API falls back to live HubSpot.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

_log = logging.getLogger(__name__)


def _parse_date_to_ms(raw: Any) -> Optional[int]:
    """Parse HubSpot date (number in ms/s, or ISO string) to epoch ms. Returns None if unset or unparseable."""
    if raw is None:
        return None
    if isinstance(raw, dict) and "value" in raw:
        raw = raw["value"]
    if raw is None:
        return None
    try:
        if isinstance(raw, (int, float)):
            ms = int(raw)
            return ms * 1000 if ms < 1e12 else ms
        s = str(raw).strip()
        if not s:
            return None
        if s.isdigit():
            ms = int(s)
            return ms * 1000 if ms < 1e12 else ms
        from datetime import datetime
        if "T" in s or "-" in s:
            normalized = s.replace("Z", "+00:00")[:26]
            dt = datetime.fromisoformat(normalized)
            return int(dt.timestamp() * 1000)
    except (TypeError, ValueError, OverflowError):
        pass
    return None


def _get_db_url() -> Optional[str]:
    return (os.getenv("DATABASE_URL") or "").strip() or None


def _get_connection():
    url = _get_db_url()
    if not url:
        return None
    try:
        import psycopg2
        if url.startswith("postgres://"):
            url = "postgresql://" + url[11:]
        conn = psycopg2.connect(url, connect_timeout=10)
        conn.autocommit = True
        return conn
    except Exception as e:
        _log.warning("Redistribute cache DB connection failed: %s", e)
        return None


def init_redistribute_cache_db() -> None:
    """Create unqualified_leads_cache table if DATABASE_URL is set."""
    if not _get_db_url():
        return
    conn = _get_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS unqualified_leads_cache (
                    lead_id TEXT PRIMARY KEY,
                    contact_id TEXT,
                    lead_type TEXT NOT NULL,
                    disqualification_reason TEXT NOT NULL,
                    date_entered_unqualified_ms BIGINT
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_redistribute_cache_lead_type_reason
                ON unqualified_leads_cache (lead_type, disqualification_reason)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_redistribute_cache_date
                ON unqualified_leads_cache (date_entered_unqualified_ms)
            """)
        _log.info("Redistribute cache table ready")
    except Exception as e:
        _log.warning("Redistribute cache init failed: %s", e)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def refresh_redistribute_cache(client) -> None:
    """
    Fetch unqualified leads from HubSpot (per lead_type), resolve contact associations,
    then truncate and repopulate unqualified_leads_cache. Call from background thread every 2 hours.
    """
    from config import (
        REDISTRIBUTE_LEAD_PIPELINE_ID,
        REDISTRIBUTE_UNQUALIFIED_STAGE_ID,
        REDISTRIBUTE_DISQUALIFICATION_PROPERTY,
        REDISTRIBUTE_DATE_ENTERED_PROPERTY,
        REDISTRIBUTE_REASONS,
        REDISTRIBUTE_LEAD_TYPES,
    )

    conn = _get_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE unqualified_leads_cache")
        rows_to_insert = []
        properties = [REDISTRIBUTE_DISQUALIFICATION_PROPERTY, REDISTRIBUTE_DATE_ENTERED_PROPERTY, "hs_object_id"]
        for lead_type in REDISTRIBUTE_LEAD_TYPES:
            filters = [
                {"propertyName": "hs_pipeline", "operator": "EQ", "value": REDISTRIBUTE_LEAD_PIPELINE_ID},
                {"propertyName": "hs_pipeline_stage", "operator": "EQ", "value": REDISTRIBUTE_UNQUALIFIED_STAGE_ID},
                {"propertyName": REDISTRIBUTE_DISQUALIFICATION_PROPERTY, "operator": "IN", "values": REDISTRIBUTE_REASONS},
                {"propertyName": "hs_lead_type", "operator": "EQ", "value": lead_type},
            ]
            filter_groups = [{"filters": filters}]
            all_lead_ids = []
            lead_date_by_id = {}
            after = None
            max_pages = 50
            for _ in range(max_pages):
                res = client.search_leads(
                    filter_groups=filter_groups,
                    properties=properties,
                    limit=100,
                    after=after,
                )
                results = res.get("results") or []
                for lead in results:
                    lid = lead.get("id")
                    if not lid:
                        continue
                    lid = str(lid)
                    all_lead_ids.append(lid)
                    props = lead.get("properties") or {}
                    raw_reason = props.get(REDISTRIBUTE_DISQUALIFICATION_PROPERTY)
                    if isinstance(raw_reason, dict) and "value" in raw_reason:
                        raw_reason = raw_reason["value"]
                    reason = (str(raw_reason or "").strip()) if raw_reason else ""
                    if reason not in REDISTRIBUTE_REASONS:
                        reason = REDISTRIBUTE_REASONS[0]
                    raw_date = props.get(REDISTRIBUTE_DATE_ENTERED_PROPERTY)
                    if isinstance(raw_date, dict) and "value" in raw_date:
                        raw_date = raw_date["value"]
                    date_ms = _parse_date_to_ms(raw_date)
                    lead_date_by_id[lid] = (reason, date_ms)
                after = (res.get("paging") or {}).get("next", {}).get("after")
                if not after or len(results) < 100:
                    break
            if not all_lead_ids:
                continue
            assoc = client.get_lead_to_contact_associations_batch(all_lead_ids)
            for lid in all_lead_ids:
                reason, date_ms = lead_date_by_id.get(lid, ("", None))
                contact_id = None
                cids = assoc.get(lid) or []
                if cids:
                    contact_id = str(cids[0])
                rows_to_insert.append((lid, contact_id, lead_type, reason, date_ms))
        if rows_to_insert:
            with conn.cursor() as cur:
                for chunk_start in range(0, len(rows_to_insert), 500):
                    chunk = rows_to_insert[chunk_start:chunk_start + 500]
                    cur.executemany(
                        """
                        INSERT INTO unqualified_leads_cache (lead_id, contact_id, lead_type, disqualification_reason, date_entered_unqualified_ms)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (lead_id) DO UPDATE SET
                            contact_id = EXCLUDED.contact_id,
                            lead_type = EXCLUDED.lead_type,
                            disqualification_reason = EXCLUDED.disqualification_reason,
                            date_entered_unqualified_ms = EXCLUDED.date_entered_unqualified_ms
                        """,
                        chunk,
                    )
            _log.info("Redistribute cache refreshed: %s rows", len(rows_to_insert))
    except Exception as e:
        _log.exception("Redistribute cache refresh failed: %s", e)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def get_counts_from_cache(
    lead_type: str,
    last_days: Optional[int] = None,
) -> Optional[dict]:
    """
    Return { "counts": { reason: n, ... } } from cache, or None if cache unavailable/empty.
    last_days filters by date_entered_unqualified_ms >= (now - last_days) in ms.
    """
    from config import REDISTRIBUTE_REASONS
    from datetime import datetime, timedelta, timezone

    conn = _get_connection()
    if not conn:
        return None
    try:
        since_ms = None
        if last_days is not None and last_days > 0:
            since_ms = int((datetime.now(timezone.utc) - timedelta(days=last_days)).timestamp() * 1000)
        with conn.cursor() as cur:
            if since_ms is not None:
                cur.execute(
                    """
                    SELECT disqualification_reason, COUNT(*)
                    FROM unqualified_leads_cache
                    WHERE lead_type = %s AND date_entered_unqualified_ms IS NOT NULL AND date_entered_unqualified_ms >= %s
                    GROUP BY disqualification_reason
                    """,
                    (lead_type, since_ms),
                )
                rows = cur.fetchall()
                total_with_date = sum(n for _, n in (rows or []))
                if total_with_date == 0:
                    # Date filter returned nothing – often means date isn't set on leads; show all-time with message
                    cur.execute(
                        """
                        SELECT disqualification_reason, COUNT(*)
                        FROM unqualified_leads_cache
                        WHERE lead_type = %s
                        GROUP BY disqualification_reason
                        """,
                        (lead_type,),
                    )
                    rows = cur.fetchall()
                    counts = {r: 0 for r in REDISTRIBUTE_REASONS}
                    for reason, n in (rows or []):
                        if reason in counts:
                            counts[reason] = int(n)
                    return {"counts": counts, "date_filter_not_applied": True, "message": "Date entered isn't set for these leads; showing all-time counts."}
            else:
                cur.execute(
                    """
                    SELECT disqualification_reason, COUNT(*)
                    FROM unqualified_leads_cache
                    WHERE lead_type = %s
                    GROUP BY disqualification_reason
                    """,
                    (lead_type,),
                )
                rows = cur.fetchall()
        counts = {r: 0 for r in REDISTRIBUTE_REASONS}
        for reason, n in (rows or []):
            if reason in counts:
                counts[reason] = int(n)
        return {"counts": counts}
    except Exception as e:
        _log.debug("Redistribute cache get_counts failed: %s", e)
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def get_lead_rows_from_cache(
    lead_type: str,
    reason: str,
    last_days: Optional[int] = None,
) -> Optional[list[dict]]:
    """
    Return [ {"lead_id": ..., "contact_id": ...}, ... ] from cache for execute, or None.
    """
    from datetime import datetime, timedelta, timezone

    conn = _get_connection()
    if not conn:
        return None
    try:
        since_ms = None
        if last_days is not None and last_days > 0:
            since_ms = int((datetime.now(timezone.utc) - timedelta(days=last_days)).timestamp() * 1000)
        with conn.cursor() as cur:
            if since_ms is not None:
                cur.execute(
                    """
                    SELECT lead_id, contact_id
                    FROM unqualified_leads_cache
                    WHERE lead_type = %s AND disqualification_reason = %s
                      AND date_entered_unqualified_ms IS NOT NULL AND date_entered_unqualified_ms >= %s
                    """,
                    (lead_type, reason, since_ms),
                )
            else:
                cur.execute(
                    """
                    SELECT lead_id, contact_id
                    FROM unqualified_leads_cache
                    WHERE lead_type = %s AND disqualification_reason = %s
                    """,
                    (lead_type, reason),
                )
            rows = cur.fetchall()
        return [{"lead_id": str(r[0]), "contact_id": str(r[1]) if r[1] else None} for r in (rows or [])]
    except Exception as e:
        _log.debug("Redistribute cache get_lead_rows failed: %s", e)
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def remove_lead_ids_from_cache(lead_ids: list[str]) -> None:
    """Remove the given lead_ids from unqualified_leads_cache (e.g. after they have been re-distributed)."""
    if not lead_ids:
        return
    conn = _get_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM unqualified_leads_cache WHERE lead_id = ANY(%s)",
                (list(lead_ids),),
            )
        _log.info("Redistribute cache: removed %s re-distributed lead(s)", len(lead_ids))
    except Exception as e:
        _log.warning("Redistribute cache remove_lead_ids failed: %s", e)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def cache_has_data() -> bool:
    """Return True if cache table exists and has at least one row."""
    conn = _get_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM unqualified_leads_cache LIMIT 1")
            return cur.fetchone() is not None
    except Exception:
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass
