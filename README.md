# Random Recipe

Mobile-first web app that picks a random recipe and shows it with step-by-step cooking instructions.

## Run locally

```bash
npm install
npm start
```

Then open http://localhost:3000 (or the port shown).

## Deploy to Railway

1. Push this repo to GitHub (see below).
2. In [Railway](https://railway.app), click **New Project** → **Deploy from GitHub repo**.
3. Select this repository. Railway will detect the Node app and use the `Procfile` to run `npx serve . -p $PORT`.
4. Add a public domain in the service **Settings** if you want a URL.

No build step required; Railway serves the static files with `serve`.
