"""File-based holidays store: staff_id, start_date, end_date, label."""
import json
import os
from datetime import date
from typing import Any, Dict, List, Optional

from config import HOLIDAYS_FILE, DATA_DIR


def _ensure_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def _load() -> List[Dict[str, Any]]:
    _ensure_dir()
    if not os.path.isfile(HOLIDAYS_FILE):
        return []
    try:
        with open(HOLIDAYS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def _save(holidays: List[Dict[str, Any]]) -> None:
    _ensure_dir()
    with open(HOLIDAYS_FILE, "w") as f:
        json.dump(holidays, f, indent=2)


def _parse_d(s: str) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s.strip()[:10])
    except Exception:
        return None


def all_holidays() -> List[Dict[str, Any]]:
    """Return list of { id, staff_id, start_date, end_date, label }."""
    return _load()


def add_holiday(staff_id: str, start_date: str, end_date: str, label: str = "") -> Dict[str, Any]:
    """Add holiday; return new record with id."""
    holidays = _load()
    new_id = str(max((int(h.get("id", 0) or 0) for h in holidays), default=0) + 1)
    rec = {
        "id": new_id,
        "staff_id": staff_id,
        "start_date": start_date.strip()[:10],
        "end_date": end_date.strip()[:10],
        "label": (label or "").strip(),
    }
    holidays.append(rec)
    _save(holidays)
    return rec


def update_holiday(holiday_id: str, staff_id: str, start_date: str, end_date: str, label: str = "") -> Optional[Dict[str, Any]]:
    holidays = _load()
    for h in holidays:
        if str(h.get("id")) == str(holiday_id):
            h["staff_id"] = staff_id
            h["start_date"] = start_date.strip()[:10]
            h["end_date"] = end_date.strip()[:10]
            h["label"] = (label or "").strip()
            _save(holidays)
            return h
    return None


def delete_holiday(holiday_id: str) -> bool:
    holidays = _load()
    for i, h in enumerate(holidays):
        if str(h.get("id")) == str(holiday_id):
            holidays.pop(i)
            _save(holidays)
            return True
    return False


def is_on_holiday_today(staff_id: str) -> bool:
    today = date.today()
    for h in _load():
        if str(h.get("staff_id")) != str(staff_id):
            continue
        start = _parse_d(h.get("start_date"))
        end = _parse_d(h.get("end_date"))
        if start and end and start <= today <= end:
            return True
    return False
