---
id: ui.tier_chips
title: Tier chips
category: interface
updated_at: 2026-08-04
summary: Which extractors ran, how many fields each contributed, and which failed.
keywords: tier chips rules gliner llm badge count amber unavailable
---

One chip per [tier](#concept.extraction-tier) that produced something on the
last turn, with a count beside it.

| Chip | Meaning |
|---|---|
| **rules** | [Deterministic patterns](#tier.rules) — the same answer on every machine |
| **GLiNER2** | [Schema-guided neural extraction](#tier.gliner2), for what the patterns missed |
| **LLM** | [Strict-JSON extraction](#tier.llm) via your own provider key, messy input only |

**The number** counts the fields that tier contributed, not the fields in the
state. `rules 2` means rules produced two of them.

**A chip that is absent** means that tier contributed nothing — usually because
it was not needed. Rules answering completely is the normal, cheap case.

**An amber "unavailable" chip** is different and important: that tier was
*attempted and did not answer*. A missing key, a timeout, an unreachable
provider. Without this chip a failed tier and a skipped tier would look
identical, and "rules only" would be ambiguous. See
[no LLM chip appearing](#trouble.no-llm-chip).
