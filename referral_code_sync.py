"""
Referral code sync.

Every 15 minutes (started by app.py) this finds HubSpot contacts where
  create_referral_code = true
generates a unique sequential code (LNNLL → LNNNLL format), writes it to
the contact's `referral_code` property, and clears `create_referral_code`.

Codes are tracked in PostgreSQL so they are never reissued.  DATABASE_URL
must be set; without it the sync logs a warning and exits.

Pagination notes
────────────────
HubSpot's Search API returns up to 100 results per page and supports cursor
pagination via `paging.next.after`, but caps a single search session at
10,000 records.  If more than 10,000 contacts need codes in one run, the
first 10,000 are processed (their flag is cleared) and the remainder are
picked up automatically in the next 15-minute run.

Error handling
──────────────
• DB failures for individual contacts are logged; the contact keeps its flag
  and is retried next run.
• HubSpot batch-update failures are retried up to 3 times with back-off
  (handled by HubSpotClient._request for 429 / 5xx).  If all retries fail
  the batch is logged; contacts in that batch retain their flag and are
  retried next run.  Any codes already claimed for failed contacts are
  "leaked" (wasted but never reused).
"""
import logging
import os
import time

from hubspot_client import HubSpotClient
from referral_code_db import claim_next_code, get_next_index, init_db

_log = logging.getLogger(__name__)

# HubSpot Search API page size (max 100)
_PAGE_SIZE = 100
# Max pages per run to stay well within the 10,000-record search cap
_MAX_PAGES = 100
# Seconds between page fetches to be polite to the API
_PAGE_SLEEP = 0.1


def run_referral_code_sync() -> None:
    """Entry point called by the background thread in app.py."""
    if not os.getenv("DATABASE_URL"):
        _log.warning("Referral code sync: DATABASE_URL not set – skipping")
        return

    if not init_db():
        _log.warning("Referral code sync: DB init failed – skipping")
        return

    _log.info(
        "Referral code sync: starting (next code index: %d)", get_next_index()
    )

    try:
        client = HubSpotClient()
    except Exception as e:
        _log.error("Referral code sync: cannot create HubSpot client – %s", e)
        return

    total_assigned = 0
    total_errors = 0
    pages_fetched = 0
    after: str | None = None

    while pages_fetched < _MAX_PAGES:
        # ── 1. Fetch a page of contacts needing a referral code ──────────────
        try:
            result = client.search_contacts(
                filter_groups=[{
                    "filters": [{
                        "propertyName": "create_referral_code",
                        "operator": "EQ",
                        "value": "true",
                    }]
                }],
                properties=["create_referral_code", "referral_code"],
                limit=_PAGE_SIZE,
                after=after,
            )
        except Exception as e:
            _log.error(
                "Referral code sync: contact search failed (page %d): %s",
                pages_fetched + 1, e,
            )
            break

        contacts = result.get("results") or []
        pages_fetched += 1

        if not contacts:
            _log.debug("Referral code sync: no contacts found on page %d", pages_fetched)
            break

        _log.info(
            "Referral code sync: page %d – %d contact(s) to process",
            pages_fetched, len(contacts),
        )

        # ── 2. Claim codes from DB and build the HubSpot batch payload ───────
        batch: list[dict] = []

        for contact in contacts:
            contact_id = contact.get("id")
            if not contact_id:
                continue

            props = contact.get("properties") or {}
            existing_code = (props.get("referral_code") or "").strip()

            if existing_code:
                # Code already set – only clear the flag (don't waste a new code)
                _log.debug(
                    "Contact %s already has referral_code '%s'; clearing flag only",
                    contact_id, existing_code,
                )
                batch.append({
                    "id": contact_id,
                    "properties": {"create_referral_code": ""},
                })
                continue

            code = claim_next_code(contact_id)
            if not code:
                _log.error(
                    "Referral code sync: failed to claim code for contact %s – will retry next run",
                    contact_id,
                )
                total_errors += 1
                continue

            batch.append({
                "id": contact_id,
                "properties": {
                    "referral_code": code,
                    "create_referral_code": "",   # empty string = clear the boolean
                },
            })

        # ── 3. Send batch updates to HubSpot (≤100 per request) ─────────────
        for chunk_start in range(0, len(batch), 100):
            chunk = batch[chunk_start: chunk_start + 100]
            assigned_in_chunk = sum(
                1 for u in chunk if "referral_code" in (u.get("properties") or {})
            )
            try:
                client.batch_update_contacts(chunk)
                total_assigned += assigned_in_chunk
                _log.debug(
                    "Referral code sync: batch chunk updated – %d assigned, %d flag-only",
                    assigned_in_chunk, len(chunk) - assigned_in_chunk,
                )
            except Exception as e:
                # _request already retried 429/5xx; this is a genuine failure
                _log.error(
                    "Referral code sync: batch update failed for %d contact(s) – %s "
                    "(they retain create_referral_code=true and will be retried next run)",
                    len(chunk), e,
                )
                total_errors += len(chunk)

        # ── 4. Follow pagination cursor ──────────────────────────────────────
        paging = result.get("paging") or {}
        next_cursor = (paging.get("next") or {}).get("after")
        if not next_cursor:
            break
        after = next_cursor
        time.sleep(_PAGE_SLEEP)

    _log.info(
        "Referral code sync complete: %d code(s) assigned, %d error(s), "
        "%d page(s) fetched. Next code index: %d",
        total_assigned, total_errors, pages_fetched, get_next_index(),
    )
