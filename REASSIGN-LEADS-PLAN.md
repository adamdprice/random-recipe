# Re-assign leads feature – implementation plan

## Summary

Allow redistributing another person’s leads from the Staff table: under each “Open leads” row, add a “Re-assign leads” row with a share icon per team. User selects which lead categories to include (Attempt 1, Attempt 2, Attempt 3, Call Back), sees a confirmation with total count and target staff, then confirms to reassign. Reassignment is done by assigning the **contact** associated with each lead to the **owner** of the chosen staff member.

---

## 1. Scope and data model assumptions

### 1.1 Source of “leads” to reassign

- **Leads** are the HubSpot **Leads** object (e.g. `/crm/v3/objects/leads`), filtered by:
  - `hubspot_owner_id` = the staff member we’re reassigning **from**
  - `hs_lead_type` = team (Inbound Lead, PIP Lead, Panther Lead, Frosties Lead) so we know which **team** the leads belong to
  - `hs_pipeline_stage` in **allowed stages** (see below)

- Each Lead has an association to a **Contact** (Lead → Contact). Reassignment = update the Contact’s `hubspot_owner_id` to the new owner (the staff member’s `hubspot_owner_id`).

### 1.2 Pipeline stages — implemented

- We **only search** leads in these pipeline stages; leads **stay in their current stage** when reassigned (we only change the contact owner). Stages: `new-stage-id`, `attempting-stage-id`, `connected-stage-id`. Config: `REASSIGN_PIPELINE_STAGES` in `config.py`.

### 1.3 Categories (Attempt 1 / 2 / 3, Call Back)

- **Lead Tags:** “Attempt 1”, “Attempt 2”, “Attempt 3” – need exact HubSpot property name(s) on the **Lead** object:
  - Option A: Three boolean properties, e.g. `attempt_1`, `attempt_2`, `attempt_3`
  - Option B: One multi-select property, e.g. `lead_tag` with values “Attempt 1”, “Attempt 2”, “Attempt 3”
  - **Action:** Confirm with you and add to config (e.g. `REASSIGN_LEAD_TAG_ATTEMPT_1`, etc. or one property + values).

- **Call Back:** Property `call_back_date` (on Lead or Contact – to be confirmed).
  - If `call_back_date` is set and is a **future date**, the lead is counted **only** under “Call Back” and **not** under Attempt 1, 2 or 3.
  - If no future `call_back_date`, the lead is categorized only by Attempt 1/2/3 (at least one tag assumed).

- **Counts in UI:** For each category (Attempt 1, Attempt 2, Attempt 3, Call Back), show how many leads will be re-assigned if that category is selected. Call Back and Attempt 1/2/3 are mutually exclusive per lead when `call_back_date` is future.

### 1.4 Target staff (who receives reassigned leads)

- **Same team only:** Staff who are in the **same Lead Team** as the leads being reassigned (team = “lead type” / `hs_lead_type` mapping, e.g. Inbound Lead → Inbound Lead Team).
- **Active and available:** Only staff with `availability` = “Available” (or equivalent) and considered active (e.g. in the Staff table and not paused).
- **Exclude the source owner:** Do not list or assign back to the person we’re reassigning from.

---

## 2. UI (frontend)

### 2.1 Staff table: new row “Re-assign leads”

- **Where:** Under the existing “Open leads” sub-row, for each staff row (both active and inactive tables).
- **Layout:** One new `<tr class="reassign-leads-row">` with:
  - First cell: label “Re-assign leads” (and optionally a small share icon).
  - One cell per team (Inbound, PIP, Panther, Frosties), aligned with the team columns above.
- **Per-team cell:**
  - If this staff is **in** that team (`lead_teams`), show a **share icon** button (e.g. “Re-assign” / share icon). Click opens the Re-assign flow for that **owner + team**.
  - If not in that team, leave the cell empty (or “—”).
- **Styling:** Reuse or extend existing table styles (e.g. `.open-leads-row`); ensure the new row is visually grouped with the staff row + open leads row (e.g. same row striping / indent).

### 2.2 Re-assign modal / flow

- **Step 1 – Choose categories**
  - Title: e.g. “Re-assign leads – [Staff name] – [Team short name]”.
  - List four options with **checkboxes** and **counts**:
    - Attempt 1 — **N** leads
    - Attempt 2 — **N** leads
    - Attempt 3 — **N** leads
    - Call Back — **N** leads
  - Counts come from backend (see API below). Counts are computed with same rules as backend (future `call_back_date` → Call Back only; else Attempt 1/2/3).
  - **Re-assign** button at bottom: **disabled** until at least one category is selected. When enabled, clicking goes to Step 2.

- **Step 2 – Confirm**
  - Message: “You are about to re-assign **M** lead(s). They will be distributed to the following staff:”
  - List of staff names (only active, available members of that team, excluding current owner).
  - If no target staff: show “No available staff in this team” and do not allow confirm.
  - Buttons: **Go back** (return to Step 1), **Confirm** (call execute API).

- **Step 3 – Done**
  - Success: “Re-assigned M leads.” Close modal and refresh staff table (and open lead counts).
  - Error: Show error message, keep modal open or allow retry.

### 2.3 APIs the frontend will call

- `GET /api/reassign/preview?owner_id=...&team=...`  
  Returns:
  - `counts`: `{ "attempt_1": n, "attempt_2": n, "attempt_3": n, "call_back": n }`
  - `target_staff`: list of `{ id, name, hubspot_owner_id }` (same team, active, available, excluding source owner).

- `POST /api/reassign/execute`  
  Body: `{ "owner_id": "...", "team": "Inbound Lead Team" (or team key), "categories": ["attempt_1", "attempt_2", "attempt_3", "call_back"] }`  
  Returns: `{ "reassigned": n, "assignments": [ { "contact_id", "owner_id", "staff_name" }, ... ] }`  
  Backend assigns contacts (associated to selected leads) to the target owners (round-robin or by existing distribution logic).

---

## 3. Backend

### 3.1 Config (config.py)

- **Pipeline stages for re-assign:**  
  `REASSIGN_PIPELINE_STAGES = ["new-stage-id", "attempting-stage-id"]` (or from env `HUBSPOT_LEAD_REASSIGN_STAGES`).
- **Lead tag / Attempt 1–3:**  
  Property name(s) for “Attempt 1”, “Attempt 2”, “Attempt 3” (e.g. three booleans or one enum – to be set once confirmed).
- **Call back:**  
  Property name `call_back_date` (Lead or Contact). If value is a date and date > today, lead counts only in “Call Back”.

### 3.2 HubSpot client (hubspot_client.py)

- **Search leads** (already exists): Extend or use with filters: `hubspot_owner_id`, `hs_lead_type`, `hs_pipeline_stage` IN allowed stages. Request properties: attempt tags, `call_back_date`, and any needed for association.
- **Get associations Lead → Contact:**  
  Use HubSpot Associations API (e.g. v4) to get associated Contact IDs for a batch of Lead IDs. Add a method e.g. `get_lead_to_contact_associations(lead_ids)` or per-lead.

### 3.3 Reassign service (new module or in app.py)

- **Preview (counts + target staff):**
  - Fetch leads for `owner_id` + team (`hs_lead_type`) + `hs_pipeline_stage` in allowed stages.
  - For each lead, compute category: if `call_back_date` is future → “call_back”; else if Attempt 1 tag → “attempt_1”, etc. (no double-counting; call_back takes precedence).
  - Return counts per category.
  - Target staff: from Staff list (cached or API), filter by same team (e.g. “Inbound Lead Team” for “Inbound Lead”), `availability` = Available, exclude `owner_id`. Return list for UI.

- **Execute:**
  - Fetch leads again with same filters, restrict to selected categories (same categorization logic).
  - For each lead, get associated Contact ID; collect unique contact IDs (one contact might have multiple leads – assign once).
  - Get target staff (same as preview). If none, return error.
  - Distribute contacts across target staff (e.g. round-robin). For each contact, `patch_contact(contact_id, { "hubspot_owner_id": new_owner_id })`. Optionally set `assign_lead` if the app uses it.
  - Optionally: refresh staff open-lead counts (e.g. call existing refresh or let next run do it).
  - Return count and assignment list for UI success message.

### 3.4 Pipeline stages and “attempting”

- You mentioned “new-stage-id attempting-stage-id attempting-stage-id” – interpreted as two stages: **new-stage-id** and **attempting-stage-id**. If you have a third stage, add it to `REASSIGN_PIPELINE_STAGES`.

---

## 4. Edge cases and notes

- **Lead without Contact:** If a Lead has no associated Contact, skip it (do not count, do not assign). Log or report in response if needed.
- **Duplicate contacts:** If two leads in the selection share the same Contact, reassign that contact once (one new owner).
- **Permissions:** Reuse existing auth; only users who can access the dashboard can run re-assign.
- **Rate limits:** Batch contact PATCH or throttle if many leads; consider HubSpot batch APIs for contacts.

---

## 5. Information needed from you

1. **Exact property names** for “Attempt 1”, “Attempt 2”, “Attempt 3” on the Lead object (e.g. `attempt_1`, `attempt_2`, `attempt_3` booleans, or one property + values).
2. **Is `call_back_date` on the Lead object or the Contact object?** (We’ll filter/count accordingly.)
3. **Exact pipeline stage value(s)** for “attempting” (e.g. `attempting-stage-id` or something else).
4. **Team ↔ hs_lead_type mapping:** Confirm we already have this (e.g. Inbound Lead Team ↔ “Inbound Lead” in `HS_LEAD_TYPES`). If any team name differs, tell us the exact value.

Once these are confirmed, implementation can use them in config and in the preview/execute logic without guessing.

---

## 6. Implementation order (suggested)

1. **Config + HubSpot:** Add config for stages, attempt tags, `call_back_date`. Add client method for Lead→Contact associations.
2. **Backend – preview:** Implement counts per category and target staff list; expose `GET /api/reassign/preview`.
3. **Backend – execute:** Implement selection by categories, resolve contacts, distribute to target staff, PATCH contacts; expose `POST /api/reassign/execute`.
4. **Frontend – row:** Add “Re-assign leads” row and share icon per team in `renderStaffRow`.
5. **Frontend – modal:** Two-step modal (categories + counts → confirm + target list → execute). Wire Re-assign button state and API calls.
6. **Testing:** Test with one team and one owner; verify counts, target list, and that contacts move to the correct owners.

End of plan.
