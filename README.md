# StateJar

> **Deterministic State-Handle Based Memory for Multi-Session Conversational Systems**
> Hackathon · Round 1 — Ideation · Deadline 15 July 2026

StateJar kills context-bloat hallucination in long LLM chats. Instead of replaying chat history, it
stores a small **structured memory state**, fingerprints it into a **deterministic handle**, persists it
**outside the model's context window**, and on each query retrieves only the **minimum-sufficient subset**
via GLiNER2 entity extraction + Graph-RAG tree traversal. The model ever sees only a **frozen system
prompt + a tiny subset**. No history replay. Ever.

---

## The problem
Modern conversational AI drifts in long, multi-session chats. The context window fills with raw
transcript, the original system prompt gets pushed out, and the model **hallucinates**. Re-sending the
full history every turn is also slow and expensive — token cost scales with thread length.

## The solution
1. Extract a **structured state** (facts, preferences, decisions, constraints, goals, unresolved, conflicts).
2. **Canonical-normalize** it (order/wording-independent).
3. Fingerprint it → **deterministic state handle** `SHA256(canonical_state + schema_version + norm_version)`.
4. Persist the full state in **MySQL, indexed by handle** — outside the context window.
5. On each query: **GLiNER2 → Graph-RAG traverse → minimum-sufficient subset → frozen system prompt + subset → LLM**.
6. Update → new handle, parent chain preserved. Conflicts kept, never overwritten. Audit log records provenance.

## USP — patent claim → module (1:1)
| Patent claim | StateJar module |
|---|---|
| Capture structured conversational state | `core/state.py` |
| Canonical normalization (identical meaning → same state) | `core/canonical.py` |
| Deterministic state handle | `core/handle.py` |
| Handle-indexed persistent storage | `core/storage.py` + `db/` |
| Eliminate full conversation replay | request pipeline (no history path) |
| Minimum-sufficient context retrieval | `core/retrieval.py` |
| Versioned memory evolution | `core/versioning.py` |
| Preserve conflicting/unresolved info | `core/conflict.py` |
| Cross-session response consistency | retrieval + frozen system prompt |
| Auditability & provenance | `core/audit.py` |

## Architecture
```
User query
   │
   ▼
[GLiNER2 entity extraction] ──► identify target topic node
   │
   ▼
[Graph-RAG tree traversal] ──► relevant branches only
   │
   ▼
[Minimum-sufficient retrieval] ──► tiny subset from MySQL (indexed by handle)
   │
   ▼
[Immutable system prompt] + [subset] ──► LLM (via BYOK gateway)
   │
   ▼
Response  +  [audit log: handle/version/subset used]
```
Full map + DB schema: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Why it wins (cuts hallucination, tokens, cost)
- **Hallucination:** the model never sees bloated history, only a frozen prompt + focused subset → no drift.
- **Tokens:** per-query input ≈ system prompt + subset, **constant** w.r.t. thread length (vs linear with replay).
- **Cost:** fewer tokens + retrieval is a SQL/cosine lookup, not an LLM call.
- **Memory that lasts like a tree:** Graph-RAG nodes/branches; new facts branch off, old nodes never overwritten (versioned handles). Cross-session recall is a graph hop, not a history scan.
- **Auditable:** every response traces to the handle + subset that shaped it.

## Security
AES-256 encrypted BYOK keys (never logged/returned in plaintext) · argon2 passwords · JWT short-lived
access + refresh rotation · email verification + password reset · RBAC (User/Admin/Owner) ·
parameterized SQL only · rate limiting · secret-scan gate in CI · redacted audit logs.

## Tech stack
Python · FastAPI · MySQL (XAMPP local → PlanetScale/Aiven prod) · GLiNER2 (local → Railway/Render) ·
Graph-RAG over MySQL nodes/edges · React + Vite · Vercel · BYOK gateway (OpenAI/Anthropic/Gemini/OpenRouter/Ollama).

---

## The 4 phases (A)
| # | Phase | Goal | Exit gate |
|---|---|---|---|
| 1 | Development | Patent core + gateway + auth + Playground, locally | every `core/` module tested + signed off; local e2e runs |
| 2 | Designing | Anthropic-style UI/UX + animation storyboards | design tokens committed; storyboards match real data flow |
| 3 | Testing | Local install + adversarial + hallucination/drift proof | `core/` coverage ≥ 90%, no High/Critical, token-delta measured |
| 4 | Deployment | Vercel + Railway(GLiNER2) + hosted MySQL; smoke test | prod smoke green, secret-scan clean, demo link live |

Detail: [`docs/PHASES.md`](docs/PHASES.md).

## Rounds (B)
| Round | Theme | Deliverables |
|---|---|---|
| R1 — Ideation (15 Jul 2026) | Solution + plan + repo | this README, [`docs/`](docs), repo, pitch video, GitHub link |
| R2 — Core MVP | Patent USP working locally | 7 `core/` modules + Graph-RAG + GLiNER2 + BYOK gateway + auth + Playground |
| R3 — Platform & UI | Productize | REST API platform, Dashboard, Admin, Stripe, module GIFs in README |
| R4 — Ship | Deploy + prove | Vercel + Railway + hosted MySQL; drift test; token-delta; live demo + pitch video |

> Round boundaries inferred from the brief (workshop PDFs extracted empty). See [`docs/ROUNDS.md`](docs/ROUNDS.md).

## Directory (F)
```
StateJar/
├── docs/{ROUND1_SOLUTION, ARCHITECTURE, PHASES, ROUNDS, ANIMATIONS, DIRECTORY}.md
├── backend/app/{main.py, config.py, core/, graph/, extract/, gateway/, auth/, api/, billing/, db/}
├── backend/{tests/, requirements.txt, .env.example}
├── frontend/{src/, package.json, vite.config.js, index.html}
├── animations/            # module GIF outputs
├── README.md  .gitignore  vercel.json
```
Include/exclude rationale: [`docs/DIRECTORY.md`](docs/DIRECTORY.md).

---

## Modules & their GIF prompts (C)

Each module below has its animation embed + the full design prompt you can copy to generate the GIF. Save each as `animations/<module>.gif` (≤800px wide, ≤3 MB, ~12 fps).

**Shared visual system (prepend to every prompt):**
> Style: minimalist Google-research-paper animation — clean cream background, thin 1.5px strokes,
> single accent color per actor, generous whitespace, no chrome. Palette: Anthropic-inspired —
> background `#F5F4EE`, ink `#1F1E1D`, clay `#C96442`, sage `#6B8E7F`, muted gold `#D9A441`.
> Humanist sans (Inter / Söhne-like), lowercase labels. Motion: ease-in-out, 600–900ms per beat,
> hold 400ms on the key idea. No sound. Loop seamlessly. Export as GIF.

### 1. State Extraction — `core/state.py`
![state-extraction](animations/state-extraction.gif)
```
Animate "Structured State Extraction."
Scene 1 (0-2s): a chat bubble appears: "I'm Ayaan. I prefer email, not calls. Budget under ₹2000.
Haven't decided delivery time." typed out character-by-character.
Scene 2 (2-5s): from the bubble, colored chips detach and float right into labeled rows:
  • "name: Ayaan" (sage chip) → row FACTS
  • "contact_mode: email" (clay chip) → row PREFERENCES
  • "budget_inr_max: 2000" (gold chip) → row CONSTRAINTS
  • "delivery_time: ?" (dashed outline chip) → row UNRESOLVED
Scene 3 (5-6s): rows settle into a tidy JSON card titled "state". Hold.
Label bottom-center: "facts · preferences · constraints · unresolved".
```

### 2. Canonical Normalization — `core/canonical.py`
![canonical-normalization](animations/canonical-normalization.gif)
```
Animate "Canonical Normalization — identical meaning, same state."
Scene 1 (0-2s): two cards slide in side by side.
  Card A: { "constraints": {"budget": 2000}, "facts": {"name": "Ayaan"} }
  Card B: { "facts": {"name":"Ayaan"}, "constraints": {"budget": 2000} }
Scene 2 (2-4s): keys in each card animate sorting alphabetically (swap positions with a soft slide),
  whitespace collapses, a "v1" schema tag snaps onto both.
Scene 3 (4-6s): both cards morph into one identical card in the center, a checkmark appears.
Label: "order & wording don't matter → one canonical form".
```

### 3. Deterministic Handle — `core/handle.py`
![handle-generation](animations/handle-generation.gif)
```
Animate "Deterministic State Handle."
Scene 1 (0-2s): the canonical JSON card sits center. Three labeled pills attach below it:
  [canonical_state] [schema_v1] [norm_v1].
Scene 2 (2-4s): the pills' contents stream into a small "SHA-256" gear box; the box spins briefly.
Scene 3 (4-6s): a single fingerprint-style code emits from the box: "shm_8f3a9c…d21".
  A lock icon clicks onto it. Hold.
Label: "SHA256(canonical_state + schema_v1 + norm_v1)".
```

### 4. Handle-Indexed Storage — `core/storage.py`
![persistent-storage](animations/persistent-storage.gif)
```
Animate "Handle-Indexed Persistent Storage."
Scene 1 (0-2s): the handle "shm_8f3a…" sits on the left; on the right a MySQL database cylinder.
Scene 2 (2-4s): the handle acts as a key — it slides into the cylinder's index slot; the full state
  JSON card drops into a row behind it. A small "outside context window" bracket encloses the DB,
  clearly separate from a faded "LLM context" box on the far left.
Scene 3 (4-5s): a second handle "shm_0000" shows as parent_handle, linked by a thin line.
Label: "full state stored by handle — outside the model's context".
```

### 5. Minimum-Sufficient Retrieval — `core/retrieval.py`
![minimum-sufficient-retrieval](animations/minimum-sufficient-retrieval.gif)
```
Animate "Minimum-Sufficient Retrieval."
Scene 1 (0-2s): a query bubble: "Book my delivery with my usual preferences."
Scene 2 (2-4s): the full state card is shown faded with many fields; three fields highlight
  (pulse clay): preferences.contact_mode, constraints.budget_inr_max, unresolved.delivery_time.
  The other fields dim and a small scissors icon trims them away.
Scene 3 (4-6s): only the three highlighted fields remain in a compact card that flies up toward a
  small "LLM" node alongside a frozen "system prompt" card.
Label: "only the subset needed — nothing more".
```

### 6. Versioned Evolution — `core/versioning.py`
![versioning](animations/versioning.gif)
```
Animate "Versioned State Evolution."
Scene 1 (0-2s): handle "shm_A" card with state {budget: 2000}.
Scene 2 (2-4s): user bubble: "Budget is now under ₹2500." A new card "shm_B" forms, state {budget: 2500}.
Scene 3 (4-6s): shm_B links to shm_A via a "parent_handle" arrow; shm_A stays unchanged (a small
  "preserved" pin). A vertical timeline grows downward: A → B.
Label: "new handle on update — old versions never overwritten".
```

### 7. Conflict Preservation — `core/conflict.py`
![conflict-preservation](animations/conflict-preservation.gif)
```
Animate "Conflict Preservation."
Scene 1 (0-2s): earlier preference chip "contact_mode: email" (sage).
Scene 2 (2-4s): new user bubble: "Call me only." A "contact_mode: call" chip (clay) appears.
Scene 3 (4-6s): instead of replacing, both stack into a "conflicts" sub-card:
  { field: contact_mode, old: email, new: call, ts }. A warning glyph marks it; nothing is deleted.
Label: "contradictions kept as first-class state — not overwritten".
```

### 8. Audit & Replay Provenance — `core/audit.py`
![audit-replay](animations/audit-replay.gif)
```
Animate "Audit & Replay Provenance."
Scene 1 (0-2s): a response bubble to the user; a dotted "provenance" line trails from it.
Scene 2 (2-5s): the line connects to an audit-log row that fills in field by field:
  request_id: req_102 · input_query: "Book my delivery" · handle_used: shm_B ·
  subset_keys: [contact_mode, budget_inr_max, delivery_time] · schema_v1 · norm_v1 · ts.
Scene 3 (5-6s): a "replay" button pulses; pressing it re-runs the same subset → same response.
Label: "which handle & subset shaped each answer — replayable".
```

### 9. Graph-RAG Traversal — `graph/traverse.py`
![graph-rag-traversal](animations/graph-rag-traversal.gif)
```
Animate "Graph-RAG Tree Traversal — the speed-of-light path."
Scene 1 (0-2s): a query bubble: "Order it again." GLiNER2 chip tags entities: [delivery, preference].
Scene 2 (2-5s): a knowledge graph of nodes (FACTS, PREFERENCES, CONSTRAINTS, UNRESOLVED) with typed
  edges fades in. The extracted entity tags light up two nodes; a clay pulse travels along edges from
  those nodes to only the connected branches; un-reached nodes stay dim.
Scene 3 (5-7s): the reached nodes' values gather into the compact subset card and fly to the LLM with
  the frozen system prompt. Un-reached graph remains faint in the background.
Label: "extract → find node → traverse branch → retrieve only what's relevant".
```

### 10. Playground (live memory view) — `frontend/`
![playground-chat](animations/playground-chat.gif)
```
Animate "Playground — live memory view."
Scene 1 (0-2s): a two-pane app shell (Anthropic cream theme). Left: chat. Right: "Live Memory" panel.
Scene 2 (2-5s): user types "I prefer WhatsApp updates, budget under ₹1500." In the right panel, a
  state card builds in real time: preferences.contact_mode=whatsapp, constraints.budget=1500. A handle
  chip "shm_…" updates; the Graph-RAG mini-tree adds two nodes.
Scene 3 (5-7s): user asks "Order it again." Right panel shows the subset highlighting (clay pulse) +
  the trimmed card sent to the model. A "session reset" pill sits top-right.
Label: "chat on the left, memory forming on the right — in real time".
```

> All prompts also live in [`docs/ANIMATIONS.md`](docs/ANIMATIONS.md).

---

## Run locally
```bash
python -m venv .venv && source .venv/Scripts/activate
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env   # fill in
uvicorn backend.app.main:app --reload
cd frontend && npm install && npm run dev
```
Health: `curl http://localhost:8000/health` → `{"status":"ok"}`.

## Deploy
Local-first: only deploy once local tests pass. Target: Vercel (API + frontend) + Railway/Render
(GLiNER2) + hosted MySQL (PlanetScale/Aiven). Set `DATABASE_URL`, `JWT_SECRET`, `AES_KEY`,
`GLINER2_URL` in the Vercel dashboard — never in git.

## Docs
[Solution](docs/ROUND1_SOLUTION.md) · [Architecture](docs/ARCHITECTURE.md) · [Phases](docs/PHASES.md) ·
[Rounds](docs/ROUNDS.md) · [Animations](docs/ANIMATIONS.md) · [Directory](docs/DIRECTORY.md)

## Status
**Round 1:** solution doc + plan + repo skeleton ✅ · pitch video + GitHub link ⏳
**Round 2** (core MVP) is next per [`docs/ROUNDS.md`](docs/ROUNDS.md).