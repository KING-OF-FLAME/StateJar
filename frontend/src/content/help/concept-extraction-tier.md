---
id: concept.extraction-tier
title: Extraction tier
category: concepts
updated_at: 2026-08-04
summary: Three extractors run in order of cost; the cheapest that succeeds wins.
keywords: tier extraction rules gliner llm cascade
---

**Definition.** One of three extractors: [rules](#tier.rules), [GLiNER2](#tier.gliner2), [LLM](#tier.llm). They run cheapest-first, and a later tier can only fill fields an earlier one left empty.

**Why it exists.** Rules are free and exact but narrow; a language model is broad but costs money and latency. Running them in order gets the coverage without paying for it on every message.

**Where you see it.** The [tier chips](#ui.tier_chips) under the tabs, one per tier that ran, with the number of fields it contributed.

**Worked example.** `My budget is 5000` is handled entirely by rules — one chip, `rules 1`. A rambling paragraph with a buried commitment may need tier 3, and you will see an `llm` chip.

**Common misunderstanding.** That a higher tier is more trusted. It is not: everything a tier proposes goes through the same type guard and the same registry. A model's guess is checked exactly as hard as a regex's.
