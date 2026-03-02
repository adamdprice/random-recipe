# Deploy Kinly Lead Distribution to Railway

## Prerequisites

- Code in a **Git repository** (e.g. GitHub) — Railway deploys from Git.
- A **Railway** account: [railway.app](https://railway.app).

## Option A: Deploy from Railway dashboard (recommended)

1. **Push your code to GitHub** (if not already).
   - If your repo root is the whole workspace, Railway will need the **root directory** set to `kinly-lead-distribution` (see step 3).

2. **Create a new project on Railway**
   - Go to [railway.app](https://railway.app) → **New Project**.
   - Choose **Deploy from GitHub repo** and select your repository.
   - If the repo root is the workspace (parent of `kinly-lead-distribution`), set **Root Directory** to `kinly-lead-distribution` in the service settings.

3. **Configure the service**
   - Railway will detect the **Procfile** and use `web: gunicorn --bind 0.0.0.0:$PORT --workers 1 app:app`.
   - It will use **Python** and **runtime.txt** (Python 3.9.18).

4. **Set environment variables**
   In the service → **Variables**, add the same variables you use locally (from `.env`). At minimum:

   - `HUBSPOT_ACCESS_TOKEN` (required)
   - `HUBSPOT_STAFF_OBJECT_ID` (optional, default: `2-194632537`)
   - `HUBSPOT_LEAD_TEAM_OBJECT_ID` (optional)
   - `HUBSPOT_LEAD_PIPELINE_STAGE` (optional, default: `new-stage-id`)

   If you use **login** (password and/or email code), also set:

   - `SESSION_SECRET` (e.g. `openssl rand -hex 32`)
   - `APP_PASSWORD_HASH` (if using password)
   - For email OTP: `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM`, and optionally `ALLOWED_EMAILS`

   For **webhooks**: set `WEBHOOK_SECRET` if you use the lead-team max_leads webhook.

5. **Deploy**
   - Railway will build and deploy on every push to the connected branch.
   - In **Settings** → **Networking**, click **Generate Domain** to get a public URL (e.g. `https://your-app.up.railway.app`).

## Option B: Deploy with Railway CLI (from this repo)

The project includes npm scripts so you don’t need a global CLI install.

1. **One-time: log in and link** (run these in your terminal; login opens a browser)
   ```bash
   cd kinly-lead-distribution
   npm run railway:login    # complete auth in the browser
   npm run railway:link     # create or link a Railway project
   ```

2. **Set variables**  
   In the [Railway dashboard](https://railway.app/dashboard): your project → **Variables** → add the same vars as your local `.env`.  
   Or via CLI: `npm run railway -- variables set HUBSPOT_ACCESS_TOKEN=your_token` (etc.).

3. **Deploy**
   ```bash
   npm run deploy
   ```
   (Or `npx @railway/cli up`.)

4. **Generate a public URL**  
   In the dashboard: your service → **Settings** → **Networking** → **Generate Domain**.

## After deploy

- Open the generated URL (e.g. `https://….up.railway.app`). If login is enabled, you’ll be redirected to `/login`.
- **HubSpot**: Ensure your HubSpot app allows the Railway domain if you use OAuth or redirects; for private app token only, no change needed.
- **Webhooks**: Update the webhook URL in HubSpot (or elsewhere) to `https://your-app.up.railway.app/api/webhooks/lead-team-max-leads` and set `WEBHOOK_SECRET` in Railway variables.
