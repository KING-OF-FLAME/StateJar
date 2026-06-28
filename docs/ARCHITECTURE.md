# StateJar — Architecture

## Component map
```
backend/app/
├── core/        # the 7 patent modules (the USP)
│   ├── state.py        # extract facts/prefs/decisions/constraints/goals/unresolved/conflicts
│   ├── canonical.py    # order-independent normalization (sort keys, standardize formats, schema ver)
│   ├── handle.py       # SHA256(canonical_state + schema_version + norm_version) -> "shm_..."
│   ├── storage.py      # handle-indexed persist/load from MySQL
│   ├── retrieval.py    # minimum-sufficient subset selection (intent -> required fields)
│   ├── versioning.py   # new handle on update, parent_handle chain preserved
│   ├── conflict.py     # retain contradictions as first-class state, never overwrite
│   └── audit.py        # log handle/version/subset used per response (provenance)
├── graph/       # Graph-RAG tree
│   ├── nodes.py        # topic nodes (typed: fact/preference/decision/...)
│   ├── edges.py        # typed relationships (parent/child/depends_on/resolves)
│   └── traverse.py     # from extracted entity -> relevant branch -> required node ids
├── extract/     # GLiNER2 client (local service or Railway/Render URL)
├── gateway/     # BYOK LLM providers + AES-256 key store + model selector
├── auth/        # email/pass, JWT, email verify, password reset, RBAC
├── api/         # REST API platform: key gen/rotate, rate limit, usage logs
├── billing/     # Stripe plans (Round 3)
├── db/          # MySQL models + migrations
└── config.py    # env-driven config (no hardcoded secrets)
```

## Request lifecycle (the happy path)
1. `POST /chat` with `{session_id, query}` + JWT.
2. `extract/` → GLiNER2 returns entities from the query.
3. `graph/traverse` → entities map to node ids → traverse to relevant branch → required fields.
4. `core/retrieval` → load current handle's state → project the minimum-sufficient subset.
5. `gateway/` → call user's BYOK provider with **frozen system prompt + subset only** (no history).
6. `core/state` → merge any new facts from this turn → `canonical` → new `handle` (parent = previous).
7. `core/audit` → write provenance: `request_id, handle_used, subset_keys, schema/norm version, ts`.
8. Return response (+ optional `memory_view` payload for the Playground).

## DB schema sketch (MySQL)
```sql
users(id, email UNIQUE, password_hash, role ENUM('user','admin','owner'),
      email_verified_at, created_at, plan)
sessions(id, user_id, current_handle, created_at)
handles(handle PK, parent_handle, state_json JSON, schema_version, norm_version, created_at, metadata)
nodes(id, handle, type, field, value, embedding BLOB)        -- Graph-RAG tree nodes
edges(id, src_node, dst_node, relation)                       -- typed relationships
audit_logs(id, request_id, user_id, handle_used, subset_keys JSON, ts)
llm_keys(id, user_id, provider, encrypted_key BLOB, created_at)  -- AES-256
api_keys(id, user_id, key_hash, last_rotated_at, revoked_at)
usage_logs(id, user_id, endpoint, tokens_in, tokens_out, ts)
```
- `state_json` is the full structured state; the handle is its content fingerprint.
- `embedding` stored as BLOB; cosine similarity computed app-side (no native vector in hosted MySQL).
- Parent chain on `handles` gives versioned, traceable evolution without overwrites.

## Why no graph database
The tree is shallow and typed (nodes/edges in two MySQL tables). A graph DB would add a second
storage engine + ops burden with no benefit at this scale — violates rule 10 (keep simple).

## Why GLiNER2 is a separate service in prod
Vercel serverless caps bundles at ~250 MB; GLiNER2 (PyTorch) exceeds that. Local dev runs it in-process;
prod runs it on Railway/Render and the backend calls it over HTTP via `GLINER2_URL`.