# Push to GitHub and deploy on Railway

## 1. Push to GitHub (one-time)

The repo **https://github.com/adamdprice/kinly-lead-distribution** is created and your code is committed locally. Push it from your machine:

```bash
cd /Users/tga/Cursor/kinly-lead-distribution
git remote -v   # should show origin → https://github.com/adamdprice/kinly-lead-distribution.git
git push -u origin main
```

(If you use SSH: `git remote set-url origin git@github.com:adamdprice/kinly-lead-distribution.git` then `git push -u origin main`.)

## 2. Deploy from Railway

1. Go to **[railway.app](https://railway.app)** → **New Project**.
2. Choose **Deploy from GitHub repo**.
3. Select **adamdprice/kinly-lead-distribution** (authorize GitHub if asked).
4. Railway will detect the **Procfile** and deploy. No need to set a root directory (the repo is the app).
5. **Variables**: In your project → your service → **Variables** → add the same keys as your local `.env` (e.g. `HUBSPOT_ACCESS_TOKEN`, `SESSION_SECRET`, SMTP vars, etc.). Paste values from your `.env`; do not commit `.env`.
6. **Public URL**: Service → **Settings** → **Networking** → **Generate Domain**.

After that, every push to `main` will redeploy automatically.
