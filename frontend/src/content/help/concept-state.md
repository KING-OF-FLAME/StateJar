---
id: concept.state
title: State
category: concepts
updated_at: 2026-08-04
summary: The structured memory for a session at one point in time.
keywords: state memory structured current
---

**Definition.** The structured set of everything StateJar currently holds for a session: sections, fields, and normalized values.

**Why it exists.** A model cannot be handed a conversation and be expected to reason reliably about what is still true. State is the answer to 'what is true now', separated from the words that established it.

**Where you see it.** The Memory State tab. Also returned by `GET /memory/state/{handle}` and by every ingest response.

**Worked example.** After `my budget is 5000 rupees`, state contains `constraints.budget.max = {currency: 'INR', value: 5000}` and nothing else.

**Common misunderstanding.** That state is a summary of the conversation. It is not a summary — nothing was compressed or paraphrased. Every value in it was extracted, type-checked and normalized.
