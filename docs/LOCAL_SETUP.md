# Running StateJar locally

Verified end to end on Windows 11 against XAMPP on 2026-08-05, at commit
`569c3df`. Every command below was executed; every number is measured, not
estimated. Where something broke, it is in [Troubleshooting](#troubleshooting)
with the actual error text.

## What you need

| | Verified with | Notes |
|---|---|---|
| Python | 3.14.3 | no lower bound declared anywhere in the repo |
| Node | 22.14.0 | `package.json` declares no `engines` field |
| npm | 10.9.2 | |
| Database | MariaDB 10.4.28 (XAMPP) | XAMPP ships **MariaDB**, not MySQL — the connection string is the same |

XAMPP's MySQL must be running on 3306. The client used below lives at
`<XAMPP>\mysql\bin\mysql.exe` — on this machine XAMPP is on `E:\`, not the
default `C:\xampp`, so adjust the path.

## 1. Database

The migrations hardcode `CREATE DATABASE statejar` and `USE statejar`
(`001_init.sql`), so the database name is not configurable without editing SQL.

```powershell
cd F:\PROJECT-WORK\FINAL_YEAR_PROJECT\statejar\db\migrations
$m = 'E:\xampp\mysql\bin\mysql.exe'
foreach ($f in '001_init.sql','003_audit_session_tag.sql','004_memory_states_per_user.sql',
                '005_api_key_lifecycle.sql','006_state_version.sql','007_user_profiles.sql') {
  Get-Content $f | & $m -u root -h 127.0.0.1 -P 3306 --database=statejar
  Write-Output "$f exit=$LASTEXITCODE"
}
```

**Pipe the file into `mysql` on stdin. Do not use `mysql -e "source file.sql"`** —
`source` prints the error and still exits 0, so every migration reports success
whether or not it applied. That is verified below in Troubleshooting.

Confirm by querying, not by trusting the exit code:

```powershell
& $m -u root -h 127.0.0.1 -P 3306 -e "SELECT 'users' t, COUNT(*) n FROM statejar.users UNION ALL SELECT 'memory_states', COUNT(*) FROM statejar.memory_states UNION ALL SELECT 'audit_logs', COUNT(*) FROM statejar.audit_logs UNION ALL SELECT 'api_keys', COUNT(*) FROM statejar.api_keys UNION ALL SELECT 'provider_keys', COUNT(*) FROM statejar.provider_keys UNION ALL SELECT 'user_profiles', COUNT(*) FROM statejar.user_profiles;"
```

Six tables must answer. `user_profiles` is the one migration 007 adds; if it is
missing, 007 did not run.

### Which is authoritative: `create_all` or the `.sql` files?

**`create_all` is.** `app/main.py::_ensure_tables()` runs on every app start
(FastAPI lifespan) and does three things: rebuilds `memory_states` for
migration 004 if it still has the old primary key, calls `metadata.create_all`
for all six table sets, then applies each later migration's `ALTER` guarded by
an `inspect()` check. A database that has never seen a `.sql` file is brought
fully up to date just by starting the app.

The `db/migrations/*.sql` files are a parallel record for operating the
database by hand. **Nothing runs them automatically** — not the app, not the
Procfile, not `railway.json`. They are useful for reviewing schema history and
for provisioning a database without booting the app, but they are not the
source of truth, and they can drift from the SQLAlchemy metadata without any
test noticing.

Two oddities in that directory worth knowing:

- **There is no `002_*.sql`.** The numbering jumps 001 → 003.
- **"007" means two different things.** The file is `007_user_profiles.sql`,
  but the comment in `_ensure_tables()` labelled "migration 007" is the Ollama
  provider-card split. Both are real; they are unrelated changes that took the
  same number.

## 2. `backend/.env`

Gitignored by `*.env`. Never commit it.

```ini
DB_URL=mysql+pymysql://root:@127.0.0.1:3306/statejar?charset=utf8mb4
JWT_SECRET=<32 random bytes, hex>
AES_KEY=<32 random bytes, base64>
EXTRACTOR_MODE=auto
```

**The setting is `DB_URL`, not `DATABASE_URL`.** `config.py` declares
`db_url: str = "mysql+pymysql://root:@localhost:3306/statejar"`, and
pydantic-settings maps that field to the `DB_URL` environment variable. A file
that says `DATABASE_URL` is ignored in silence, and because the code default
points at the same host, the app still starts and still answers — it simply
uses the default. That is why the failure presents as "nothing persists"
rather than as a configuration error.

Using `127.0.0.1` rather than `localhost` is deliberate: it differs from the
code default, so a connection that reports `127.0.0.1` proves the file was
read. Verify it:

```bash
cd backend
./.venv/Scripts/python.exe -c "from app.config import get_settings; print(get_settings().db_url.split('@')[-1])"
# 127.0.0.1:3306/statejar?charset=utf8mb4
```

Generate real values (do not reuse these):

```bash
python -c "import secrets,base64; print('JWT_SECRET=' + secrets.token_hex(32)); print('AES_KEY=' + base64.b64encode(secrets.token_bytes(32)).decode())"
```

**If a `.env` already exists, keep its `AES_KEY` and `JWT_SECRET`.**
`provider_keys.encrypted_key` is AES-GCM encrypted with `AES_KEY`, so a new key
silently orphans every saved provider credential — `decrypt_key` raises and the
row is unreadable. A new `JWT_SECRET` invalidates every issued token.

## 3. `frontend/.env.local`

Gitignored by `*.local`.

```ini
VITE_API_URL=http://localhost:8000
```

Without this the frontend falls back to `.env.example`'s
`https://api.statejar.com` for the API-docs samples, and `api.js` uses relative
`/api/v1` paths that `vite.config.js` proxies to port 8000. Both setups work;
the explicit one is clearer and makes `/api-docs` show local URLs. Vite reads
it at **startup**, so restart `npm run dev` after changing it.

Setting it makes calls cross-origin (`:5173` → `:8000`), which is fine:
`config.py`'s `cors_origins` already lists `http://localhost:5173` and
`http://127.0.0.1:5173`.

## 4. Install

```bash
cd backend
python -m venv .venv
./.venv/Scripts/python.exe -m pip install --upgrade pip
./.venv/Scripts/python.exe -m pip install -r requirements.txt

cd ../frontend
npm install
```

## 5. Run

Two terminals, both left running:

```bash
# backend
cd backend && ./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# frontend
cd frontend && npm run dev
```

| | URL |
|---|---|
| App | http://localhost:5173 |
| API | http://127.0.0.1:8000/api/v1 |
| Health | http://127.0.0.1:8000/api/v1/health |

The frontend's Vite proxy targets port 8000 specifically
(`vite.config.js`), so the backend must be on 8000 unless you edit that file.

## 6. Tests

```bash
cd backend
DB_URL="sqlite:///:memory:" ./.venv/Scripts/python.exe -m pytest -q -p no:randomly
```

Measured: **740 passed, 1 skipped** in 101s.

Use the sqlite URL. The default points at MySQL and each `TestClient` costs
about four seconds of connect timeout otherwise.

You do **not** need `EXTRACTOR_MODE=rules`. `tests/conftest.py` has an autouse
fixture that pins `EXTRACTOR_MODE=rules` and `RETRIEVER_SEMANTIC=false` for the
whole suite, precisely so a developer with the ML extras installed gets the
same handles as CI. Verified: with GLiNER installed and no env var set,
`tests/test_extractor.py tests/golden` ran 176 tests in 1.10s — GLiNER never
loaded, which takes 25s.

## 7. GLiNER2 (tier 2) — optional

```bash
cd backend
./.venv/Scripts/python.exe -m pip install -r requirements-ml.txt
```

Pulls CPU-only torch. Verify by **importing and loading**, never by reading a
status field:

```bash
./.venv/Scripts/python.exe -c "
from app.memory.extractor import _load_gliner_model, _predict
m = _load_gliner_model()
print(type(m).__name__)
print(_predict(m, 'My name is Rahul Sharma and I work at Tata Consultancy Services in Mumbai'))"
```

Measured on this machine: torch 2.13.0+cpu, gliner 0.2.28,
`UniEncoderSpanGLiNER` loaded in **25.5s** on first call (downloads
`urchade/gliner_multi-v2.1` from HuggingFace; cached afterwards), returning

```
{'text': 'Rahul Sharma',              'label': 'person name',  'score': 0.985}
{'text': 'Tata Consultancy Services', 'label': 'organization', 'score': 0.973}
{'text': 'Mumbai',                    'label': 'city',         'score': 0.902}
```

Note the organization came back whole. The rule tier caps a proper-noun capture
at two words and refuses the truncation, so GLiNER2 is what recovers a
three-word employer.

`extraction_tiers: {"gliner2": "ok"}` in an ingest response is **not** proof the
model ran on its own — read it together with `extraction_source`, and prefer
the import check above.

## Troubleshooting

Everything here actually happened during this setup.

### `ModuleNotFoundError: No module named 'respx'` — 4 collection errors

```
ImportError while importing test module '...tests/test_gateway.py'.
E   ModuleNotFoundError: No module named 'respx'
```

`respx` is imported by `test_gateway`, `test_integration`, `test_ollama` and
`test_providers` but was missing from `requirements.txt`, so a fresh clone
could not run the suite at all. Fixed — `respx>=0.21` is now declared. If you
have an older checkout: `pip install respx`.

### Migrations report success but did nothing

```powershell
& mysql -u root -e "source 006_state_version.sql"
# ERROR 1060 (42S21): Duplicate column name 'state_version'
# exit=0        <-- error printed, exit code still zero
```

`mysql -e "source ..."` does not propagate SQL errors to the exit code. Pipe
the file on stdin instead and the same statement exits 1. Any script that runs
migrations with `source` and checks `$LASTEXITCODE` reports green regardless.

### `Duplicate column name` re-running migrations

001, 003 and 007 are idempotent (`CREATE TABLE IF NOT EXISTS`,
`ADD COLUMN IF NOT EXISTS`). **004, 005 and 006 are not** — they fail on a
database that already has them:

| | Re-run on an up-to-date DB |
|---|---|
| `001_init.sql` | exit 0 |
| `003_audit_session_tag.sql` | exit 0 |
| `004_memory_states_per_user.sql` | exit 1 — `Duplicate column name 'id'` |
| `005_api_key_lifecycle.sql` | exit 1 — `Duplicate column name 'label'` |
| `006_state_version.sql` | exit 1 — `Duplicate column name 'state_version'` |
| `007_user_profiles.sql` | exit 0 |

These are safe failures — MySQL `ALTER TABLE` is atomic per statement, so
nothing half-applies — but a migration runner that stops on first error will
stop here. `_ensure_tables()` handles all three correctly because it checks
`inspect()` before altering.

### `POST /chat` returns 400 on a fresh account

```json
{"detail":"No OpenAI API key saved — add one on the API Keys page to chat."}
```

Expected, not a bug: chat spends *your* provider credit and there is no key
saved yet. Two ways forward locally:

- Save a real provider key on **API Keys**, or
- use the keyless demo provider — `{"provider":"demo","model":"scripted-demo"}` —
  which returns a scripted reply but a **real** handle, real disclosed subset
  and a real audit row.

Ingest, retrieval, restore and the dashboard all work with no provider key at
all. Only `/chat` needs one.

### Audit log is empty

Audit rows are written on **disclosure**, not on ingest. Nothing appears until
something discloses state: `POST /chat`, or `POST /memory/query` with
`{"audit": true}`. Ingesting ten turns still leaves the audit log empty, which
is correct — nothing left the system.

### Two databases named similarly

This machine already had a `statejar_dev` schema from an older iteration of the
project (`alembic_version`, `tenants`, `subscriptions`, `conversation_states`).
It is unrelated to the current app and nothing reads it. The live database is
`statejar`.

## Verified working

Walked in a browser against `http://localhost:5173`, not asserted from code:

- signup → lands on `/profile?onboarding`; login → `/dashboard`
- profile saved, **hard reload**, all four fields still present; row confirmed
  in MySQL with `SELECT`
- one playground turn populates memory state and shows a handle
- restoring that handle into a fresh session re-derives the **identical**
  handle and the same facts
- dashboard draws no charts with no data (existing empty-state copy kept), and
  draws "Fields by namespace" and "Handle lineage" once states exist
- audit log renders entries with handle, disclosed-field chips and Replay
- Profile is reachable from the console sidebar
- the span-binding fix holds with GLiNER2 live: "My name is Rahul Sharma and
  I'm from Pune" then "I'm Mumbai based now, switching from Senior Software
  Engineer to Engineering Manager" ends at
  `{"city": "Mumbai", "name": "Rahul Sharma", "role": "Senior Software Engineer"}`
  — the name survives and the city is not "Senior Software"
