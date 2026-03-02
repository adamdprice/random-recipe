# Kinly Lead Distribution

Replicates the N8N "Kinly Lead Smart Distribution Process" and provides a dashboard to manage Lead Team `max_leads`, Staff availability, and dry-run (test) distribution without assigning contacts.

## Setup

1. Copy `.env.example` to `.env` and set:
   - `HUBSPOT_ACCESS_TOKEN` (required) – HubSpot private app token.
   - `HUBSPOT_STAFF_OBJECT_ID` (default `2-194632537`).
   - `HUBSPOT_LEAD_TEAM_OBJECT_ID` – your Lead Team custom object type ID when available.
   - `HUBSPOT_LEAD_PIPELINE_STAGE` (default `new-stage-id`) – pipeline stage for new leads.

2. **(Optional) Login**: To protect the dashboard and API, set `SESSION_SECRET` (e.g. `openssl rand -hex 32`) and at least one sign-in method:
   - **Password**: set `APP_PASSWORD_HASH` (bcrypt hash). Generate one with:
     ```bash
     python -c "import bcrypt; print(bcrypt.hashpw(b'yourpassword', bcrypt.gensalt()).decode())"
     ```
   - **Passwordless (one-time code to email)**: set `SMTP_HOST`, `SMTP_PORT` (default 587), `SMTP_USER`, `SMTP_PASSWORD`, and `EMAIL_FROM`. Optionally set `ALLOWED_EMAILS` (comma-separated) so only those addresses can request a code. Users enter their email, receive a 6-digit code, and sign in with it (code expires in 15 minutes).
   If `SESSION_SECRET` and at least one method are set, the app requires sign-in. Otherwise the app is open.

3. Install and run:
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # or .venv\Scripts\activate on Windows
   pip install -r requirements.txt
   python app.py
   ```
   API: http://localhost:5000. Dashboard at http://localhost:5000/ (no build required). If login is enabled, visiting `/` redirects to `/login`.

## API

- `GET /api/health` – Health and config check.
- `GET /api/lead-teams` – List Lead Teams (requires `HUBSPOT_LEAD_TEAM_OBJECT_ID`).
- `PATCH /api/lead-teams/<id>` – Update `max_leads` (body: `{ "max_leads": 10 }`).
- `GET /api/staff` – List Staff Members.
- `PATCH /api/staff/<id>` – Update `availability` (body: `{ "availability": "Available" }`).
- `POST /api/distribute?dry_run=true` – Run distribution for a contact (body: `{ "contactId": "123" }`). With `dry_run=true` returns intended actions only; no HubSpot writes.

## Test mode

Use `POST /api/distribute?dry_run=true` with `{ "contactId": "<contact_id>" }` to see what would have been done (contact assignments and staff updates) without assigning any contacts.

## Live run and security

- **Triggering a real run**: Call `POST /api/distribute?dry_run=false` with `{ "contactId": "<contact_id>" }`. The contact is used only to resolve `hubspot_owner_id`; distribution then assigns unassigned contacts to that owner. You can expose this as a webhook (e.g. from HubSpot or N8N) or a “Run for this owner” button in the dashboard.
- **Securing**: Use the built-in login: set `SESSION_SECRET` and either a password (`APP_PASSWORD_HASH`) or passwordless email codes (SMTP + `EMAIL_FROM`; optionally `ALLOWED_EMAILS`). Session cookie is HttpOnly, Secure in production, SameSite=Lax. Do not expose the app publicly without auth if the token can perform writes.
- **Second-loop**: The N8N workflow includes a second pass (“Find largest lead pool” and assign from that pool after a wait). This replication implements the first pass only; a second loop can be added later if you need identical behaviour.

## Deploy to Railway (or similar)

**Is Railway secure?** Yes, for this use case. Railway gives you HTTPS, injects env vars at runtime (so secrets aren’t in the image), and runs in a private network by default. You should still treat the dashboard as sensitive and restrict who can open the deployed URL if it can change HubSpot data.

### 1. Prepare the repo

- Commit the app (including `Procfile`, `requirements.txt`, `runtime.txt`). The `Procfile` runs the app with Gunicorn; the app reads `PORT` from the environment.

### 2. Create a Railway project

1. Go to [railway.app](https://railway.app) and sign in.
2. **New Project** → **Deploy from GitHub repo** (or upload this folder).
3. Connect the repo and choose the branch; Railway will detect Python and use the `Procfile`.

### 3. Set environment variables

In the Railway project → your service → **Variables**, add the same keys you use in `.env` (no `.env` file is needed; Railway injects these):

- **Required:** `HUBSPOT_ACCESS_TOKEN`
- **Required:** `HUBSPOT_LEAD_TEAM_OBJECT_ID`
- **Required:** `HUBSPOT_STAFF_OBJECT_ID` (or leave default `2-194632537` if that’s your Staff object)
- Optional: `HUBSPOT_LEAD_PIPELINE_STAGE`, `WEBHOOK_SECRET`, `FLASK_DEBUG` (leave unset or `0` in production)
- Optional: `DATABASE_URL` – when set (e.g. Railway **Add PostgreSQL**), staff, lead teams and owners are cached in a `hubspot_cache` table for 3 minutes so the dashboard is faster and HubSpot API is used less. If unset, every request hits HubSpot.
- Optional login: `SESSION_SECRET` and either `APP_PASSWORD_HASH` (password) or SMTP + `EMAIL_FROM` (passwordless email code); optionally `ALLOWED_EMAILS` (comma-separated)

Do **not** commit `.env` or any file containing the token.

### 4. Deploy and get the URL

- Railway builds and runs the app and assigns a URL (e.g. `https://your-app.up.railway.app`).
- You can add a **custom domain** in the service settings if you want.

### 5. Optional: lock down the app

- Set `SESSION_SECRET` and `APP_PASSWORD_HASH` in Railway Variables to enable the built-in login screen. Users will be redirected to `/login` and must enter the password before using the dashboard or API (health and webhook remain unauthenticated).
- For the webhook `POST /api/webhooks/lead-team-max-leads`, set `WEBHOOK_SECRET` in Railway and configure HubSpot to send that value in the `X-Webhook-Secret` header so only HubSpot can call it.
