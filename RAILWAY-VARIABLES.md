# Variables to add in Railway

Add these in **Railway → Your Service → Variables**. Copy each **Variable** name exactly; set the **Value** (secrets from your local `.env` or generate where noted).

**If you see "Something went wrong loading data (server returned HTML, status 500)":** the app is returning an error page instead of JSON. Open **Railway → Your Service → Deployments → View Logs** to see the Python traceback. Most often the cause is a **missing or invalid variable**. Set at least the **Required** variables below and redeploy.

## Required for the app

| Variable | Value |
|----------|--------|
| `HUBSPOT_ACCESS_TOKEN` | Your HubSpot private app token (required; without it most API calls will 500) |

## Required for login (dashboard will redirect to login; without these you cannot sign in)

| Variable | Value |
|----------|--------|
| `SESSION_SECRET` | Long random string (e.g. `openssl rand -hex 32`) – **required if you want to use the dashboard** |
| `SMTP_HOST` | e.g. `smtp.sendgrid.net` (for email one-time code login) |
| `SMTP_USER` | e.g. `apikey` (SendGrid) |
| `SMTP_PASSWORD` | Your SendGrid API key |
| `EMAIL_FROM` | Sender email (e.g. `noreply@yourdomain.com`) |

## Optional

| Variable | Value |
|----------|--------|
| `ALLOWED_EMAILS` | Comma-separated emails that can request a code (or leave unset for any) |
| `SMTP_PORT` | `587` (default) |
| `HUBSPOT_STAFF_OBJECT_ID` | `2-194632537` (or your ID) |
| `HUBSPOT_LEAD_TEAM_OBJECT_ID` | Your Lead Team object ID |
| `HUBSPOT_LEAD_PIPELINE_STAGE` | `new-stage-id` (or your stage) |
| **Re-Distribute tab** | Get these from HubSpot: **Settings → Objects → Leads → Pipelines** |
| `REDISTRIBUTE_LEAD_PIPELINE_ID` | Your Lead pipeline ID (default `lead-pipeline-id` if unset) |
| `REDISTRIBUTE_UNQUALIFIED_STAGE_ID` | Unqualified stage ID (default `unqualified-stage-id` if unset) |
| `REDISTRIBUTE_NEW_STAGE_ID` | Stage ID to move leads to after re-distribute (default `new-stage-id` if unset) |
| `WEBHOOK_SECRET` | Only if using the lead-team webhook |
| `DATABASE_URL` | PostgreSQL connection URL (e.g. from Railway **Add PostgreSQL**). When set, staff/lead-teams/owners are cached in DB for 3 minutes so the dashboard loads faster and HubSpot is called less often. |
| `HUBSPOT_STAFF_HOLIDAYS_PROPERTY` | Name of a **Staff** custom object property (e.g. `holidays` or `blocked_dates`). Use a **Multi-line text** or **Rich text** field in HubSpot. When set, holidays are stored on each staff record in HubSpot instead of a local file, so they persist across deploys. Create the property in HubSpot first, then set this variable. |
| `ENABLE_BACKGROUND_DISTRIBUTION` | **Production (main):** leave unset or `true` so the app runs the 6‑minute background refresh (staff counts, holidays, distribution). **Staging:** set to `false` so staging does not run background distribution and only production does. |

---

Railway does not auto-load these from the repo; add each variable manually in the Variables tab using the names above.

## Checklist for "500 / server returned HTML"

1. **Railway → Your Service → Variables** – ensure `HUBSPOT_ACCESS_TOKEN` is set (and for login: `SESSION_SECRET`, `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM`).
2. **Railway → Deployments → [latest] → View Logs** – look for a Python traceback; it will show the exact error (e.g. missing token, DB connection failed).
3. If you added **PostgreSQL** and set `DATABASE_URL`, ensure the DB is running and the URL is correct (Railway usually sets this automatically when you add the Postgres plugin and reference it in Variables).
4. Redeploy after changing variables (Variables take effect on the next deploy).
