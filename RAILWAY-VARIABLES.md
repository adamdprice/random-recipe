# Variables to add in Railway

Add these in **Railway → Your Service → Variables**. Copy each **Variable** name exactly; set the **Value** (secrets from your local `.env` or generate where noted).

## Required for the app

| Variable | Value |
|----------|--------|
| `HUBSPOT_ACCESS_TOKEN` | Your HubSpot private app token |

## Required for email login (one-time code)

| Variable | Value |
|----------|--------|
| `SESSION_SECRET` | Long random string (e.g. `openssl rand -hex 32`) |
| `SMTP_HOST` | e.g. `smtp.sendgrid.net` |
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
| `WEBHOOK_SECRET` | Only if using the lead-team webhook |
| `DATABASE_URL` | PostgreSQL connection URL (e.g. from Railway **Add PostgreSQL**). When set, staff/lead-teams/owners are cached in DB for 3 minutes so the dashboard loads faster and HubSpot is called less often. |
| `HUBSPOT_STAFF_HOLIDAYS_PROPERTY` | Name of a **Staff** custom object property (e.g. `holidays` or `blocked_dates`). Use a **Multi-line text** or **Rich text** field in HubSpot. When set, holidays are stored on each staff record in HubSpot instead of a local file, so they persist across deploys. Create the property in HubSpot first, then set this variable. |
| `ENABLE_BACKGROUND_DISTRIBUTION` | **Production (main):** leave unset or `true` so the app runs the 6‑minute background refresh (staff counts, holidays, distribution). **Staging:** set to `false` so staging does not run background distribution and only production does. |

---

Railway does not auto-load these from the repo; add each variable manually in the Variables tab using the names above.
