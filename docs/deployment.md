# StateJar — Production Deployment Guide

Stack: **Backend** FastAPI on Railway · **Database** Railway MySQL plugin · **Frontend** React/Vite on Vercel · **Domain** your `statejar` domain via Vercel.

Prerequisites: the `statejar/` folder pushed to a GitHub repository, a [Railway](https://railway.app) account, a [Vercel](https://vercel.com) account, and your custom domain's DNS panel.

> Repo layout note: the backend lives in `statejar/backend` and the frontend in `statejar/frontend`. Both platforms need that subdirectory set as the project root — called out in each step below.

---

## 0. Push to GitHub (if not done yet)

```bash
cd F:\PROJECT-WORK\FINAL_YEAR_PROJECT\statejar
git init
git add .
git commit -m "StateJar initial release"
git remote add origin https://github.com/<your-username>/statejar.git
git push -u origin main
```

`.gitignore` already excludes `.env` — confirm before pushing:

```bash
git status --ignored | findstr .env   # backend/.env must appear under ignored
```

---

## 1. Railway — MySQL database

1. Railway dashboard → **New Project** → **Deploy MySQL** (the MySQL plugin).
2. Open the MySQL service → **Variables** tab. Note these values:
   - `MYSQLHOST`, `MYSQLPORT`, `MYSQLUSER` (usually `root`), `MYSQLPASSWORD`, `MYSQLDATABASE` (usually `railway`).
3. **Run the migration.** Open the MySQL service → **Data** tab → **Query**, and paste the contents of `db/migrations/001_init.sql` **minus the first two statements** (`CREATE DATABASE … ; USE statejar;`) — Railway already puts you inside the `railway` database. Run it.
   - Alternative from your PC (needs `mysql` client, e.g. from XAMPP at `C:\xampp\mysql\bin`):
     ```bash
     mysql -h MYSQLHOST -P MYSQLPORT -u root -pMYSQLPASSWORD railway < db/migrations/001_init.sql
     ```
     If you use this route, first comment out the `CREATE DATABASE` and `USE statejar;` lines, or the tables land in the wrong schema.
4. Verify: in the Data tab you should see 5 tables — `users`, `memory_states`, `audit_logs`, `api_keys`, `provider_keys`.

## 2. Railway — backend deploy

1. In the same Railway project → **New** → **GitHub Repo** → select your `statejar` repo.
2. Service → **Settings** → **Root Directory** → set to `backend`.
   (`backend/railway.json` and `backend/Procfile` already define the start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, healthcheck `/api/v1/health`.)
3. Service → **Variables** → add:

   | Variable | Value |
   |---|---|
   | `DB_URL` | `mysql+pymysql://root:${{MySQL.MYSQLPASSWORD}}@${{MySQL.MYSQLHOST}}:${{MySQL.MYSQLPORT}}/${{MySQL.MYSQLDATABASE}}` |
   | `JWT_SECRET` | output of `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
   | `AES_KEY` | another fresh `secrets.token_urlsafe(48)` output (⚠ never change after users save provider keys — it decrypts them) |
   | `CORS_ORIGINS` | `["https://statejar.vercel.app"]` — you will extend this in step 5 |

   The `${{MySQL.…}}` references resolve automatically to the plugin's values (use the private/internal host if offered — faster and free of egress fees).
4. Deploy (happens automatically on save). Wait for the build, then open the service's **Settings → Networking → Generate Domain** to get a public URL like `https://statejar-api.up.railway.app`.
5. Smoke test:
   ```bash
   curl https://statejar-api.up.railway.app/api/v1/health
   # → {"status":"ok"}
   ```

## 3. Vercel — frontend deploy

1. Vercel dashboard → **Add New → Project** → import the `statejar` GitHub repo.
2. **Root Directory** → `frontend`. Framework preset: **Vite** (auto-detected). Build command `npm run build`, output `dist` (defaults are fine). `frontend/vercel.json` already handles the SPA rewrite so deep links like `/playground` work.
3. **Environment Variables** → add:

   | Variable | Value |
   |---|---|
   | `VITE_API_URL` | `https://statejar-api.up.railway.app` (your Railway URL, **no trailing slash**) |

   > Vite bakes env vars in at build time — if you change `VITE_API_URL` later, trigger a **Redeploy**.
4. Deploy. You get `https://statejar.vercel.app` (or similar).
5. Quick check: open the URL, sign up, log in — if login works, CORS and the API URL are correctly wired.

## 4. Connect the custom domain

1. Vercel project → **Settings → Domains** → **Add** → enter your domain (e.g. `statejar.in`, plus `www.statejar.in` if desired).
2. At your registrar's DNS panel, add what Vercel shows you:
   - Apex/root: `A` record → `76.76.21.21`
   - `www`: `CNAME` → `cname.vercel-dns.com`
3. Wait for Vercel to show **Valid Configuration** (DNS can take minutes to a few hours); HTTPS certificates are automatic.

## 5. Lock down CORS to the final domains

Back in Railway → backend service → **Variables** → update:

```
CORS_ORIGINS=["https://statejar.vercel.app","https://statejar.in","https://www.statejar.in"]
```

(Replace with your real domain. Keep it a strict JSON array — single quotes or trailing commas break parsing.) Railway redeploys automatically. Local dev is unaffected: the code's built-in default already allows `http://localhost:5173`, and the Vite proxy is same-origin anyway.

## 6. End-to-end smoke test

On `https://<your-domain>`:

1. **Sign up** with a fresh email → lands on the dashboard.
2. **API Keys** → save an OpenRouter key → it comes back masked as `sk-or-••••…XXXX`.
3. **Playground**, session-1 → send: `My name is Ayaan, I prefer email, budget ₹2000` → Memory State tab shows facts/preferences/constraints and a `shm_…` handle.
4. **+ New session** → send: `Book my delivery` → Retrieved Context tab shows only the minimal subset (contact_mode + budget) with the tokens-saved badge — cross-session memory working.
5. **Audit tab** shows the request with handle + subset keys.
6. From a terminal, confirm CORS is actually locked:
   ```bash
   curl -s -i -X OPTIONS https://statejar-api.up.railway.app/api/v1/health -H "Origin: https://evil.example" -H "Access-Control-Request-Method: GET" | findstr access-control
   # → no access-control-allow-origin header for the foreign origin
   ```

All six pass → production is live.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Frontend loads but every API call fails with a network/CORS error | `VITE_API_URL` missing or wrong on Vercel (redeploy after fixing), or your domain missing from `CORS_ORIGINS` on Railway |
| `500` on signup/login | `DB_URL` wrong or migration not run — check Railway MySQL Data tab for the 5 tables |
| Logins invalidated after redeploy | `JWT_SECRET` changed — keep it stable |
| “no provider key saved” after redeploy despite saving one earlier | `AES_KEY` changed — old encrypted keys can't be decrypted; users must re-save keys |
| Railway healthcheck fails on deploy | Check deploy logs; usually a missing env var crashing startup |
