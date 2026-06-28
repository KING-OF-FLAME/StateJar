# StateJar — Round 1 Solution Document

> Hackathon Round 1 — Ideation · Solution Submission · Deadline 15 July 2026
> Patent: *Deterministic State-Handle Based Memory for Multi-Session Conversational Systems*

## 1. The problem
Modern conversational AI drifts in long, multi-session chats. The model's context window fills with
raw transcript, the original system prompt gets pushed out, and the model **hallucinates**. Re-sending
the full history every turn is also slow and expensive (token cost scales with thread length).

## 2. The solution
StateJar stops feeding chat history to the model. Instead it stores a small **structured memory state**
(facts, preferences, decisions, constraints, goals, unresolved items, conflicts), normalizes it to a
**canonical form** (order/wording-independent), and fingerprints it into a **deterministic state handle**
(`SHA256(canonical_state + schema_version + norm_version)`). The full state lives in MySQL, **outside**
the model's context window. On each new query, GLiNER2 extracts entities → the Graph-RAG tree traverses
to the relevant branch → only the **minimum-sufficient subset** is retrieved and sent to the LLM alongside
an **immutable system prompt**. No history replay. Ever.

## 3. USP — mapped 1:1 to patent claims
| Patent claim | StateJar module |
|---|---|
| Capture structured conversational state [10] | `core/state.py` |
| Canonical normalization (identical meaning → same state) [11],[22] | `core/canonical.py` |
| Deterministic state handle [12],[22],[72] | `core/handle.py` |
| Handle-indexed persistent storage [13],[24] | `core/storage.py` + `db/` |
| Eliminate full conversation replay [14] | request pipeline (no history path) |
| Minimum-sufficient context retrieval [15],[25],[90] | `core/retrieval.py` |
| Versioned memory evolution [16],[26],[105] | `core/versioning.py` |
| Preserve conflicting/unresolved info [17],[111] | `core/conflict.py` |
| Cross-session response consistency [18] | retrieval + frozen system prompt |
| Auditability & provenance [19],[27],[126] | `core/audit.py` |

## 4. Architecture (high level)
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
Full component map + DB schema: `docs/ARCHITECTURE.md`.

## 5. How it cuts hallucination, tokens, and cost
- **Hallucination:** the model never sees bloated history, only a frozen prompt + a focused subset.
  No context drift → no drift-driven invention. (Phase 3 proves this with a prompt-immutability test.)
- **Tokens:** per-query input ≈ system prompt + subset, **constant** w.r.t. thread length, vs linear
  growth with naive replay. Phase 3 measures the delta for the pitch video.
- **Cost:** tokens ↓ → API spend ↓. Retrieval is a SQL + cosine lookup, not an LLM call.
- **Memory "remembers forever like a tree":** the Graph-RAG tree stores every fact as a node with
  typed edges; new facts branch off, old nodes are never overwritten (versioned handles keep history).
  Cross-session recall is a graph hop, not a history scan.

## 6. Security
- BYOK LLM keys encrypted at rest (AES-256); never logged or returned in plaintext.
- Auth: email/password (argon2), JWT short-lived access + refresh rotation, email verification, password reset.
- RBAC: User / Admin / Owner. Parameterized SQL only. Rate limiting on API + auth. Secret-scan gate in CI.
- Audit logs redact sensitive fields; provenance records handle/version/subset, not full state.

## 7. Tech stack
Python + FastAPI · MySQL (XAMPP local → PlanetScale/Aiven prod) · GLiNER2 (local → Railway/Render prod)
· Graph-RAG over MySQL nodes/edges · React + Vite · Vercel deploy · BYOK gateway (OpenAI/Anthropic/Gemini/OpenRouter/Ollama).

## 8. Roadmap (rounds)
See `docs/ROUNDS.md`. R1 = this document + plan + repo. R2 = patent core + gateway + Playground.
R3 = API platform + billing + Admin. R4 = deploy + pitch video.

## 9. Advice & key decisions (D)
1. **Frozen system prompt is the real hallucination killer** — keep it short, never inject history.
2. **AES-256 on BYOK keys; redact audit logs** — security is a rule, not a feature.
3. **Defer Stripe/billing to Round 3** — it's not the patent USP and adds scope risk.
4. **Pitch video arc:** problem (10s) → handle+subset demo (animated) → token-cost delta vs replay → trophy story.
5. **Re-extract the workshop PDFs before Round 2** — round boundaries here are inferred from the brief,
   not the official workshop guidelines (the extract files came through empty).

## 10. Round 1 deliverables status
- [x] Solution document (this file)
- [x] Architecture + plan + directory (`docs/`)
- [x] Repo skeleton (README, backend/frontend stubs, deploy config)
- [ ] Pitch video — produced from `docs/ANIMATIONS.md` prompts + screen recording (follow-up)
- [ ] GitHub repo link — push this folder and paste the URL into the submission