# StateJar — The 4 Phases (A)

Each phase has entry/exit criteria and a verification step. The phase-loop runs
write → verify → test → audit → gate on every unit of work until the exit criteria pass.

| # | Phase | Goal | Verifying agents | Exit gate |
|---|---|---|---|---|
| 1 | **Development** | Implement patent core + gateway + auth + Playground, locally | code-writer → code-verifier → test-runner → security-auditor | every `core/` module tested + signed off; local e2e runs |
| 2 | **Designing** | Unique Anthropic-style UI/UX + animation storyboards | animation-designer + code-verifier | design tokens committed; storyboards match real data flow |
| 3 | **Testing** | Local install + adversarial + hallucination/drift proof | test-runner + security-auditor | `core/` coverage ≥ 90%, no High/Critical, token-delta measured |
| 4 | **Deployment** | Vercel + Railway(GLiNER2) + hosted MySQL; smoke test | security-auditor + test-runner | prod smoke green, secret-scan clean, demo link live |

## How the loop keeps quality (rule 3 + E)
- No file is "done" until `code-verifier` has read it line-by-line and confirmed it matches the patent
  claim in its docstring (see the claim map in `docs/ROUND1_SOLUTION.md`).
- Verifiers **default to fail** when uncertain; the writer must prove correctness.
- A phase only exits when its tests + lint + secret scan are all green.

## Order note
Phases overlap in practice (design tokens can start while core is finishing), but a phase's **exit
gate** is sequential — Phase 4 cannot exit until Phase 3 is green (rule 8: local first, then deploy).