"""
PostgreSQL-backed storage for staff holidays and saved availability.

Used by holidays.set_storage() when DATABASE_URL is configured.
Holidays are stored per staff in a staff_holidays table; saved availability used
for restoring availability after a holiday is stored in holiday_saved_availability.
"""
import logging
import os
from typing import Any, Dict, List

_log = logging.getLogger(__name__)


def _get_db_url() -> str | None:
    return (os.getenv("DATABASE_URL") or "").strip() or None


def _get_connection():
    """Return a new DB connection or None if DATABASE_URL is unset/invalid."""
    url = _get_db_url()
    if not url:
        return None
    try:
        import psycopg2

        # Railway can use postgres://; psycopg2 prefers postgresql://
        if url.startswith("postgres://"):
            url = "postgresql://" + url[11:]
        conn = psycopg2.connect(url)
        conn.autocommit = True
        return conn
    except Exception as e:  # pragma: no cover - defensive
        _log.warning("Holidays DB connection failed: %s", e)
        return None


def init_holidays_db() -> None:
    """Create holidays tables if DATABASE_URL is set. Safe to call at startup."""
    if not _get_db_url():
        return
    conn = _get_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS staff_holidays (
                    id UUID PRIMARY KEY,
                    staff_id TEXT NOT NULL,
                    start_date DATE NOT NULL,
                    end_date DATE NOT NULL,
                    label TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS holiday_saved_availability (
                    staff_id TEXT PRIMARY KEY,
                    availability TEXT NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        _log.info("Holidays DB tables ready")
    except Exception as e:  # pragma: no cover - defensive
        _log.warning("Holidays DB init failed: %s", e)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def holidays_load_all() -> Dict[str, Any]:
    """
    Load all holidays and saved availability from DB.

    Returns:
      {
        "holidays": [
          {"id": str, "staff_id": str, "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD", "label": str},
          ...
        ],
        "saved_availability": { staff_id: availability, ... }
      }
    """
    conn = _get_connection()
    if not conn:
        return {"holidays": [], "saved_availability": {}}
    holidays: List[Dict[str, Any]] = []
    saved: Dict[str, str] = {}
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, staff_id, start_date, end_date, label "
                "FROM staff_holidays ORDER BY start_date, staff_id"
            )
            for row in cur.fetchall():
                hid, staff_id, start_date, end_date, label = row
                holidays.append(
                    {
                        "id": str(hid),
                        "staff_id": str(staff_id),
                        "start_date": start_date.isoformat() if start_date else None,
                        "end_date": end_date.isoformat() if end_date else None,
                        "label": label or "",
                    }
                )
            cur.execute(
                "SELECT staff_id, availability FROM holiday_saved_availability"
            )
            for staff_id, availability in cur.fetchall():
                saved[str(staff_id)] = availability
        return {"holidays": holidays, "saved_availability": saved}
    except Exception as e:  # pragma: no cover - defensive
        _log.warning("Holidays DB load failed: %s", e)
        return {"holidays": [], "saved_availability": {}}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def holidays_save_all(data: Dict[str, Any]) -> None:
    """
    Save full snapshot of holidays + saved_availability to DB.
    This replaces all existing rows (sufficient for small datasets).
    """
    conn = _get_connection()
    if not conn:
        return
    holidays = data.get("holidays") or []
    saved = data.get("saved_availability") or {}
    try:
        with conn.cursor() as cur:
            # Replace holidays
            cur.execute("DELETE FROM staff_holidays")
            for h in holidays:
                hid = h.get("id")
                staff_id = h.get("staff_id")
                start_date = h.get("start_date")
                end_date = h.get("end_date")
                label = h.get("label")
                if not hid or not staff_id or not start_date or not end_date:
                    continue
                cur.execute(
                    """
                    INSERT INTO staff_holidays (id, staff_id, start_date, end_date, label)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (str(hid), str(staff_id), start_date, end_date, label),
                )
            # Replace saved availability
            cur.execute("DELETE FROM holiday_saved_availability")
            for staff_id, availability in saved.items():
                cur.execute(
                    """
                    INSERT INTO holiday_saved_availability (staff_id, availability)
                    VALUES (%s, %s)
                    """,
                    (str(staff_id), str(availability)),
                )
    except Exception as e:  # pragma: no cover - defensive
        _log.warning("Holidays DB save failed: %s", e)
    finally:
        try:
            conn.close()
        except Exception:
            pass

