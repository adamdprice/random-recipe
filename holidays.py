"""
Staff holiday / blocked dates. Stored in a JSON file; used to auto-set availability.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import date, datetime
from typing import Any

_log = logging.getLogger(__name__)

# Data file next to this module's parent (app dir)
_app_dir = os.path.dirname(os.path.abspath(__file__))
_data_dir = os.path.join(_app_dir, "data")
HOLIDAYS_PATH = os.path.join(_data_dir, "holidays.json")
_LOCK = threading.Lock()


def _ensure_data_dir() -> None:
    os.makedirs(_data_dir, exist_ok=True)


def _load() -> dict[str, Any]:
    _LOCK.acquire()
    try:
        if not os.path.isfile(HOLIDAYS_PATH):
            return {"holidays": [], "saved_availability": {}}
        with open(HOLIDAYS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        _log.warning("Failed to load holidays: %s", e)
        return {"holidays": [], "saved_availability": {}}
    finally:
        _LOCK.release()


def _save(data: dict[str, Any]) -> None:
    _ensure_data_dir()
    _LOCK.acquire()
    try:
        with open(HOLIDAYS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    finally:
        _LOCK.release()


def _today() -> date:
    return date.today()


def _parse_d(d: str | None) -> date | None:
    if not d:
        return None
    try:
        if isinstance(d, date):
            return d
        return datetime.strptime(d[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _date_in_range(d: date, start: date, end: date) -> bool:
    return start <= d <= end


def list_holidays(staff_id: str | None = None) -> list[dict]:
    data = _load()
    holidays = data.get("holidays") or []
    if staff_id is not None:
        holidays = [h for h in holidays if str(h.get("staff_id")) == str(staff_id)]
    return holidays


def get_holiday(holiday_id: str) -> dict | None:
    for h in _load().get("holidays") or []:
        if str(h.get("id")) == str(holiday_id):
            return h
    return None


def add_holiday(staff_id: str, start_date: str, end_date: str, label: str = "") -> dict:
    start = _parse_d(start_date)
    end = _parse_d(end_date)
    if not start or not end:
        raise ValueError("Invalid start_date or end_date")
    if end < start:
        raise ValueError("end_date must be on or after start_date")
    data = _load()
    holidays = data.get("holidays") or []
    import uuid
    new_id = str(uuid.uuid4())
    new_holiday = {
        "id": new_id,
        "staff_id": str(staff_id),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "label": (label or "").strip(),
    }
    holidays.append(new_holiday)
    data["holidays"] = holidays
    _save(data)
    return new_holiday


def update_holiday(holiday_id: str, start_date: str | None = None, end_date: str | None = None, label: str | None = None) -> dict | None:
    data = _load()
    holidays = data.get("holidays") or []
    for i, h in enumerate(holidays):
        if str(h.get("id")) == str(holiday_id):
            if start_date is not None:
                start = _parse_d(start_date)
                if not start:
                    raise ValueError("Invalid start_date")
                h["start_date"] = start.isoformat()
            if end_date is not None:
                end = _parse_d(end_date)
                if not end:
                    raise ValueError("Invalid end_date")
                h["end_date"] = end.isoformat()
            if label is not None:
                h["label"] = label.strip()
            start = _parse_d(h.get("start_date"))
            end = _parse_d(h.get("end_date"))
            if start and end and end < start:
                raise ValueError("end_date must be on or after start_date")
            data["holidays"] = holidays
            _save(data)
            return h
    return None


def delete_holiday(holiday_id: str) -> bool:
    data = _load()
    holidays = data.get("holidays") or []
    saved = data.get("saved_availability") or {}
    before = len(holidays)
    holidays = [h for h in holidays if str(h.get("id")) != str(holiday_id)]
    if len(holidays) < before:
        # Remove saved availability for this staff if they have no other holidays covering today
        data["holidays"] = holidays
        _save(data)
        return True
    return False


def is_staff_on_holiday_today(staff_id: str) -> bool:
    today = _today()
    for h in list_holidays(staff_id):
        start = _parse_d(h.get("start_date"))
        end = _parse_d(h.get("end_date"))
        if start and end and _date_in_range(today, start, end):
            return True
    return False


def get_saved_availability() -> dict[str, str]:
    return (_load().get("saved_availability") or {}).copy()


def set_saved_availability(staff_id: str, availability: str) -> None:
    data = _load()
    saved = data.get("saved_availability") or {}
    saved[str(staff_id)] = availability
    data["saved_availability"] = saved
    _save(data)


def clear_saved_availability(staff_id: str) -> None:
    data = _load()
    saved = data.get("saved_availability") or {}
    saved.pop(str(staff_id), None)
    data["saved_availability"] = saved
    _save(data)


def apply_holiday_availability(client: Any, staff_object_id: str, staff_list: list[dict]) -> dict:
    """
    For each staff: if today is in one of their holidays, set HubSpot availability to Unavailable
    (and save previous availability). If today is not in any holiday and we had saved availability,
    restore it and clear saved.
    Returns {"set_unavailable": n, "restored": m} counts of staff actually updated.
    """
    from hubspot_client import HubSpotClient
    today = _today()
    saved = get_saved_availability()
    set_unavailable = 0
    restored = 0
    for s in staff_list:
        sid = str(s.get("id") or "")
        if not sid:
            continue
        current_availability = (s.get("availability") or "").strip()
        on_holiday = is_staff_on_holiday_today(sid)
        if on_holiday:
            if current_availability.lower() != "unavailable":
                set_saved_availability(sid, current_availability or "Available")
                try:
                    client.patch_custom_object(staff_object_id, sid, {"availability": "Unavailable"})
                    set_unavailable += 1
                except Exception as e:
                    _log.warning("Failed to set staff %s Unavailable for holiday: %s", sid, e)
        else:
            if sid in saved:
                try:
                    client.patch_custom_object(staff_object_id, sid, {"availability": saved[sid]})
                    restored += 1
                except Exception as e:
                    _log.warning("Failed to restore staff %s availability: %s", sid, e)
                clear_saved_availability(sid)
    return {"set_unavailable": set_unavailable, "restored": restored}
