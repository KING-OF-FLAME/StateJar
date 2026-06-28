# StateJar — Final Directory Structure (F)

Simple and short on purpose (rule 10). Round 1 creates folders + stubs; Round 2 implements modules.

```
StateJar/
├── docs/
│   ├── ROUND1_SOLUTION.md     # the submitted solution document
│   ├── ARCHITECTURE.md        # component map + request lifecycle + DB schema
│   ├── PHASES.md              # the 4 phases (A)
│   ├── ROUNDS.md              # round-wise roadmap (B)
│   ├── ANIMATIONS.md          # per-module GIF prompts (C)
│   └── DIRECTORY.md           # this file (F)
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI entry (health route in R1)
│   │   ├── config.py          # env-driven config
│   │   ├── core/              # 7 patent modules (R2)
│   │   ├── graph/             # Graph-RAG tree: nodes, edges, traverse (R2)
│   │   ├── extract/           # GLiNER2 client (R2)
│   │   ├── gateway/           # BYOK LLM providers + AES-256 key store (R2)
│   │   ├── auth/              # JWT, email verify, password reset, RBAC (R2)
│   │   ├── api/               # REST API platform: keys, rate limit, logs (R3)
│   │   ├── billing/           # Stripe plans (R3)
│   │   └── db/                # MySQL models + migrations
│   ├── tests/                 # pytest, per-module (R2+)
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── App.jsx            # landing stub (R1)
│   │   └── styles/            # design tokens (R2 Phase 2)
│   ├── package.json
│   └── vite.config.js
├── animations/                # module GIF outputs for README
├── README.md
├── .gitignore
└── vercel.json
```

## What to include (and why)
- **`backend/app/core/`** — the 7 patent modules = the entire USP. Non-negotiable.
- **`backend/app/graph/`** — the Graph-RAG "tree theory" the brief is built on.
- **`backend/app/gateway/` + `auth/`** — BYOK + RBAC are named features.
- **`frontend/` (React + Vite)** — justified: live memory view, dashboard, admin are interactive.
- **`docs/`** — Round 1 deliverable is a solution document; plan + directory + animation prompts too.
- **`animations/`** — explicit ask (challenge #6).
- **`vercel.json`** — rule 8 (deploy to Vercel).

## What NOT to add (and why)
- **No separate graph database** (Neo4j etc.) — the tree is shallow + typed; MySQL nodes/edges suffice
  (rule 10). Adding a graph DB doubles the storage/ops surface for no gain.
- **No microservice split beyond GLiNER2** — one FastAPI app keeps it simple; only GLiNER2 is external
  because Vercel serverless can't bundle it.
- **No Redis / message queue** in R1–R2 — not needed at this scale; revisit only if rate-limiting or
  jobs demand it.
- **No Stripe/billing code in R2** — deferred to R3; it's not the patent USP and adds scope risk.
- **No Docker in R1** — local-first uses XAMPP + venv; containerization is a Phase 4 option, not now.
- **No `.env` in git** — `.env.example` only; real secrets live in Vercel dashboard (rule 5).
- **No default-theme UI boilerplate** — the brief requires a unique Anthropic-style design; skip
  generic component-kit themes (Phase 2 builds the tokens).