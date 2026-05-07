"""
PostgreSQL-backed store for referral code generation and tracking.

Maintains a sequential counter so codes are issued in order and never reused.
Requires DATABASE_URL to be set; if absent the sync will skip gracefully.

Code format:
  5-char (indices 0 → 1,423,655):   LNNLL  (e.g. A11AA … Z99ZZ)
  6-char (indices 1,423,656 → 14,236,559): LNNNLL (e.g. A111AA … Z999ZZ)
  Wraps back to index 0 if both ranges are exhausted (extremely unlikely).

Letters: A–Z (26).  Digits: 1–9 (9, zero excluded for readability).
"""
import logging
import os
import threading

_log = logging.getLogger(__name__)
_init_lock = threading.Lock()

# ── Code alphabet ──────────────────────────────────────────────────────────────
_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"  # 26
_DIGITS = "123456789"                    # 9  (no zero)

_TOTAL_5 = 26 * 9 * 9 * 26 * 26         # 1,423,656  (LNNLL)
_TOTAL_6 = 26 * 9 * 9 * 9 * 26 * 26     # 12,812,904 (LNNNLL)
_TOTAL = _TOTAL_5 + _TOTAL_6             # 14,236,560


def index_to_code(n: int) -> str:
    """Convert a sequential integer index to a referral code string.

    Indices 0 … _TOTAL_5-1  → 5-char LNNLL  (A11AA … Z99ZZ)
    Indices _TOTAL_5 … _TOTAL-1 → 6-char LNNNLL (A111AA … Z999ZZ)
    Wraps modulo _TOTAL if n >= _TOTAL.

    The rightmost positions vary fastest so the sequence is:
      A11AA, A11AB, …, A11AZ, A11BA, …, A11ZZ, A12AA, …, Z99ZZ
    """
    n = n % _TOTAL
    if n < _TOTAL_5:
        # LNNLL – decode right-to-left (fast → slow)
        p4 = n % 26; n //= 26  # rightmost letter
        p3 = n % 26; n //= 26
        p2 = n % 9;  n //= 9
        p1 = n % 9;  n //= 9
        p0 = n % 26                       # leftmost letter
        return _LETTERS[p0] + _DIGITS[p1] + _DIGITS[p2] + _LETTERS[p3] + _LETTERS[p4]
    else:
        # LNNNLL
        n -= _TOTAL_5
        p5 = n % 26; n //= 26
        p4 = n % 26; n //= 26
        p3 = n % 9;  n //= 9
        p2 = n % 9;  n //= 9
        p1 = n % 9;  n //= 9
        p0 = n % 26
        return _LETTERS[p0] + _DIGITS[p1] + _DIGITS[p2] + _DIGITS[p3] + _LETTERS[p4] + _LETTERS[p5]


# ── Database helpers ───────────────────────────────────────────────────────────

def _get_db_url() -> str | None:
    return (os.getenv("DATABASE_URL") or "").strip() or None


def _get_connection(autocommit: bool = True):
    """Return a fresh psycopg2 connection, or None if DATABASE_URL is unset / unreachable."""
    url = _get_db_url()
    if not url:
        return None
    try:
        import psycopg2  # type: ignore
        if url.startswith("postgres://"):
            url = "postgresql://" + url[11:]
        conn = psycopg2.connect(url, connect_timeout=10)
        conn.autocommit = autocommit
        return conn
    except Exception as e:
        _log.warning("Referral code DB connection failed: %s", e)
        return None


def init_db() -> bool:
    """Create tables if they don't exist. Safe to call repeatedly. Returns True on success."""
    if not _get_db_url():
        return False
    conn = _get_connection(autocommit=True)
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS referral_code_counter (
                    id   INT PRIMARY KEY DEFAULT 1,
                    next_index BIGINT NOT NULL DEFAULT 0,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            # Seed the single counter row
            cur.execute("""
                INSERT INTO referral_code_counter (id, next_index)
                VALUES (1, 0)
                ON CONFLICT (id) DO NOTHING
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS referral_codes_issued (
                    code       VARCHAR(10)  PRIMARY KEY,
                    contact_id VARCHAR(32)  NOT NULL,
                    issued_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS referral_codes_issued_contact_idx
                ON referral_codes_issued (contact_id)
            """)
        _log.info("Referral code tables ready")
        return True
    except Exception as e:
        _log.warning("Referral code DB init failed: %s", e)
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


def claim_next_code(contact_id: str) -> str | None:
    """Atomically reserve the next sequential code for *contact_id*.

    Uses SELECT … FOR UPDATE to prevent races across threads / dyno replicas.
    Returns the code string, or None if the DB is unavailable.
    """
    conn = _get_connection(autocommit=False)
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            # Lock counter row for the duration of this transaction
            cur.execute(
                "SELECT next_index FROM referral_code_counter WHERE id = 1 FOR UPDATE"
            )
            row = cur.fetchone()
            if not row:
                conn.rollback()
                return None

            idx = int(row[0])
            code = index_to_code(idx)

            cur.execute(
                "INSERT INTO referral_codes_issued (code, contact_id) VALUES (%s, %s)",
                (code, str(contact_id)),
            )
            cur.execute(
                "UPDATE referral_code_counter SET next_index = %s, updated_at = NOW() WHERE id = 1",
                (idx + 1,),
            )
        conn.commit()
        _log.debug("Claimed referral code %s for contact %s (index %d)", code, contact_id, idx)
        return code
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        _log.warning("claim_next_code failed for contact %s: %s", contact_id, e)
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def get_next_index() -> int:
    """Return the current counter value (next index to be issued). For monitoring only."""
    conn = _get_connection(autocommit=True)
    if not conn:
        return 0
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT next_index FROM referral_code_counter WHERE id = 1")
            row = cur.fetchone()
        return int(row[0]) if row else 0
    except Exception as e:
        _log.warning("get_next_index failed: %s", e)
        return 0
    finally:
        try:
            conn.close()
        except Exception:
            pass
