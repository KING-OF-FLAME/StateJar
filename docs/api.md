# StateJar Developer API

Give any application deterministic, auditable memory over HTTP. You send
conversation text; StateJar extracts structured state, addresses it by a
content hash, and returns only the minimal subset a later query needs.

Everything below is copy-pasteable. Set your base URL once:

```bash
export STATEJAR_URL=http://localhost:8000      # or your deployed origin
```

## 1. Get an API key

Sign in to the console, open **API Keys → Developer API**, and press
**Generate new key**. The key looks like this:

```
sj_live_Xy7pQ2r8KdN4vLm1TgHs0BwZaEcFjUiOpYnRxVqWtSb
```

It is shown **once**. StateJar stores only its SHA-256 hash, so a lost key
cannot be recovered — generate a new one and revoke the old.

```bash
export STATEJAR_KEY=sj_live_...
```

Send it as `X-API-Key` on every request:

```
X-API-Key: sj_live_...
```

## 2. Ingest — turn text into structured state

`POST /api/v1/memory/ingest`

```bash
curl -s -X POST "$STATEJAR_URL/api/v1/memory/ingest" \
  -H "X-API-Key: $STATEJAR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
        "session_tag": "user-42",
        "text": "My name is Ayaan, budget under ₹2000. I prefer email."
      }'
```

```json
{
  "handle": "shm_18c8fecaf5dacf38deda0914ecdb1b38b40566c1",
  "parent_handle": null,
  "state": {
    "constraints": { "budget_inr_max": 2000 },
    "facts": { "name": "Ayaan" },
    "preferences": { "contact_mode": "email" },
    "norm_version": "v1",
    "schema_version": "v1"
  },
  "conflicts": [],
  "extraction_source": "rules"
}
```

The `handle` is a content address: identical state always produces an
identical handle. Ingest the same text again and you get the same handle
back. Send new information for the same `session_tag` and StateJar mints a
*new* handle whose `parent_handle` points at the previous one — history is
appended, never overwritten.

## 3. Query — retrieve the minimum a question needs

`POST /api/v1/memory/query`

```bash
curl -s -X POST "$STATEJAR_URL/api/v1/memory/query" \
  -H "X-API-Key: $STATEJAR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
        "session_tag": "user-42",
        "query": "What is my budget?",
        "audit": true
      }'
```

```json
{
  "handle_used": "shm_18c8fecaf5dacf38deda0914ecdb1b38b40566c1",
  "subset": { "constraints": { "budget_inr_max": 2000 } },
  "metadata": {
    "intents": ["budget"],
    "retrieval_mode": "intent_map",
    "subset_keys": ["constraints.budget_inr_max"],
    "fields_dropped": 4,
    "token_estimate_saved_pct": 73.9
  },
  "audit_id": "7272c2ea8d0c44e18c914184996bf843"
}
```

`subset` is the only thing you need to put in a model's context — not the
transcript, not the whole profile. `audit: true` records the disclosure in
the audit trail and returns its `audit_id`, so you can prove later exactly
what was shared.

## 4. Chat — let StateJar assemble the context for you

`POST /api/v1/chat`

Requires a provider key saved in the console (**API Keys → OpenRouter**).
StateJar retrieves the minimal subset, builds the system context, calls the
model, and writes the audit row in one round trip.

```bash
curl -s -X POST "$STATEJAR_URL/api/v1/chat" \
  -H "X-API-Key: $STATEJAR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
        "session_tag": "user-42",
        "query": "Book my delivery with my usual preferences",
        "model": "meta-llama/llama-3.3-70b-instruct:free"
      }'
```

```json
{
  "response": "Booking with your saved preferences — I'll email you the confirmation and keep it under ₹2000.",
  "handle_used": "shm_18c8fecaf5dacf38deda0914ecdb1b38b40566c1",
  "subset_keys": ["preferences.contact_mode", "constraints.budget_inr_max"],
  "audit_id": "4b8e77…"
}
```

`subset_keys` tells you precisely which fields reached the model.

## Other endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/v1/usage` | Requests today, total states, audit rows, estimated tokens saved |
| `GET` | `/api/v1/memory/versions?session_tag=user-42` | The handle chain for a session, oldest first |
| `GET` | `/api/v1/memory/state/{handle}` | Any state you own, by handle |
| `GET` | `/api/v1/audit?limit=50` | What was disclosed, when, to which model |
| `GET` | `/api/v1/memory/stats` | Console summary |

```bash
curl -s "$STATEJAR_URL/api/v1/usage" -H "X-API-Key: $STATEJAR_KEY"
```

```json
{
  "requests_today": 3,
  "total_states": 1,
  "total_audit_rows": 3,
  "est_tokens_saved": 87
}
```

Interactive reference: `$STATEJAR_URL/docs`.

## Scope of an API key

A key authenticates the **data plane** — memory, chat, audit, usage. It
deliberately cannot reach account management: issuing more keys, listing
keys, and reading your provider key all stay console-only (JWT). A leaked
key cannot mint itself a successor or exfiltrate your OpenRouter credit.
Revoke it from **API Keys → Developer API**; revocation takes effect on the
next request.

## Rate limits

| Endpoint | Limit | Keyed by |
|----------|-------|----------|
| `/api/v1/chat` | 60/hour | API key (or user) |
| `/api/v1/auth/login` | 5/minute | IP |
| `/api/v1/auth/signup` | 10/hour | IP |

Other endpoints are unlimited. Over the limit returns `429`.

## Errors

| Status | Meaning |
|--------|---------|
| `401` | Missing, unknown, or revoked key |
| `404` | No state for this user yet, or an unknown handle |
| `422` | Malformed body — see `detail` for the offending field |
| `429` | Rate limited |
| `502` | The upstream model provider failed; `detail` carries its message |

Errors are always `{"detail": "..."}`.

## Notes

- `session_tag` is any string you choose to partition a user's memory
  (`user-42`, `ticket-991`). Queries fall back to the user's most recent
  state across sessions when a tag has none of its own.
- Handles are not capabilities. Knowing one grants nothing; every read is
  authorised against the key's owner.
- Raw transcripts are never stored. StateJar persists extracted structured
  state only, and rejects any payload carrying transcript-shaped keys.
