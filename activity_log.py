"""File-based activity log: append-only entries with time, message, event, details."""
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from config import ACTIVITY_LOG_FILE, DATA_DIR

MAX_ENTRIES = 2000


def _ensure_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def _load() -> List[Dict[str, Any]]:
    _ensure_dir()
    if not os.path.isfile(ACTIVITY_LOG_FILE):
        return []
    try:
        with open(ACTIVITY_LOG_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def _save(entries: List[Dict[str, Any]]) -> None:
    _ensure_dir()
    with open(ACTIVITY_LOG_FILE, "w") as f:
        json.dump(entries[-MAX_ENTRIES:], f, indent=2)


def log(event: str, message: str, details: Optional[Dict[str, Any]] = None) -> None:
    entries = _load()
    entries.append({
        "time": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "event": event,
        "message": message,
        "details": details or {},
    })
    _save(entries)


def get_entries(limit: int = 50) -> List[Dict[str, Any]]:
    entries = _load()
    return list(reversed(entries[-limit:]))
