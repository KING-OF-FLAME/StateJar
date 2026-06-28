# StateJar — Round-wise Roadmap (B)

> **Caveat:** the workshop guideline PDFs (`_workshop_extract.txt`, `_workshop2.txt`) extracted empty,
> so round boundaries below are **inferred from the brief**. Re-extract those PDFs (OCR) before Round 2
> and adjust this table to the official round definitions.

| Round | Theme | Deliverables | Maps to phases |
|---|---|---|---|
| **R1 — Ideation** (deadline 15 Jul 2026) | Solution + plan + repo | Solution doc (`ROUND1_SOLUTION.md`), architecture, 4-phase plan, per-module GIF prompts, directory structure, repo skeleton, **pitch video**, **GitHub link** | (planning only) |
| **R2 — Core MVP** | Patent USP working locally | 7 `core/` modules + Graph-RAG tree + GLiNER2 + BYOK gateway + auth (JWT/email/RBAC) + Playground (live memory view) | Phase 1, start Phase 2 |
| **R3 — Platform & UI** | Productize | REST API platform (keys/rate-limit/logs), Dashboard, Admin panel, Stripe plans, design system + module GIFs in README | Phase 2 done, Phase 3 |
| **R4 — Ship** | Deploy + prove | Vercel + Railway(GLiNER2) + hosted MySQL; adversarial + hallucination/drift test; token-cost delta; live demo + pitch video final | Phase 3, Phase 4 |

## What "done" means per round
- **R1:** submission packet uploaded (solution doc + pitch video + GitHub URL).
- **R2:** `verify-phase 1` green; a user can sign up, chat across two sessions, and see memory persist
  with a deterministic handle + minimum-sufficient subset (proven by tests).
- **R3:** `verify-phase 2` green; API platform rate-limits and logs; Admin can suspend/override;
  README shows the module GIFs.
- **R4:** `verify-phase 3` + `verify-phase 4` green; live demo URL in README; pitch video embedded.

## Staging principle (rule 2 + 8)
Build the directory and features incrementally, round by round. Local first; only when a round's
local gate is green do we cut a prod deployment. No big-bang deploy.