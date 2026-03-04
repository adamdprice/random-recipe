"""
HubSpot read cache backed by PostgreSQL.
Stores staff, lead_teams, and owners with a TTL; API reads use cache when fresh, else fetch from HubSpot and update cache.
Set DATABASE_URL (e.g. from Railway Postgres) to enable. When unset, cache is disabled (get returns None).
"""
import json
import logging
import os
import threading

_log = logging.getLogger(__name__)

# TTL in seconds; data older than this is treated as stale
CACHE_TTL_SECONDS = 180  # 3 minutes

_db_lock = threading.Lock()
_connection = None


def _get_db_url():
    return (os.getenv("DATABASE_URL") or "").strip() or None


def _get_connection():
    """Return a DB connection; caller must not hold it across requests. Thread-safe for one connection per thread."""
    global _connection
    url = _get_db_url()
    if not url:
        return None
    try:
        import psycopg2
        # Railway Postgres may use postgres://; psycopg2 expects no scheme or postgresql://
        if url.startswith("postgres://"):
            url = "postgresql://" + url[11:]
        # Avoid hanging forever if DB is unreachable (e.g. Railway Postgres slow/unreachable)
        conn = psycopg2.connect(url, connect_timeout=10)
        conn.autocommit = True
        return conn
    except Exception as e:
        _log.warning("HubSpot cache DB connection failed: %s", e)
        return None


def init_db():
    """Create hubspot_cache table if it doesn't exist. Safe to call at startup."""
    url = _get_db_url()
    if not url:
        return
    conn = _get_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS hubspot_cache (
                    cache_key VARCHAR(64) PRIMARY KEY,
                    data JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
        _log.info("HubSpot cache table ready")
    except Exception as e:
        _log.warning("HubSpot cache init failed: %s", e)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def cache_get(key: str):
    """
    Return cached data dict if present and not older than CACHE_TTL_SECONDS, else None.
    When DATABASE_URL is not set, returns None.
    """
    conn = _get_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT data, EXTRACT(EPOCH FROM (NOW() - updated_at)) AS age_seconds FROM hubspot_cache WHERE cache_key = %s",
                (key,),
            )
            row = cur.fetchone()
        if not row:
            return None
        data, age_seconds = row
        if age_seconds is not None and age_seconds > CACHE_TTL_SECONDS:
            return None
        return data if isinstance(data, dict) else (json.loads(data) if isinstance(data, str) else None)
    except Exception as e:
        _log.debug("HubSpot cache get %s failed: %s", key, e)
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def cache_set(key: str, data: dict):
    """Store data in cache. No-op when DATABASE_URL is not set."""
    conn = _get_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO hubspot_cache (cache_key, data, updated_at)
                VALUES (%s, %s::jsonb, NOW())
                ON CONFLICT (cache_key) DO UPDATE SET data = EXCLUDED.data, updated_at = NOW()
                """,
                (key, json.dumps(data)),
            )
    except Exception as e:
        _log.warning("HubSpot cache set %s failed: %s", key, e)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def cache_invalidate(*keys: str):
    """Remove cache entries so next read refetches from HubSpot. No-op when DATABASE_URL is not set."""
    if not keys:
        return
    conn = _get_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM hubspot_cache WHERE cache_key = ANY(%s)",
                (list(keys),),
            )
    except Exception as e:
        _log.warning("HubSpot cache invalidate failed: %s", e)
    finally:
        try:
            conn.close()
        except Exception:
            pass
