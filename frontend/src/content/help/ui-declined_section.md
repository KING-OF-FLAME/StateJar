---
id: ui.declined_section
title: The declined section
category: interface
updated_at: 2026-08-04
summary: Values StateJar refused to store, each with the reason.
keywords: declined unmapped rejected refused not stored reasons
---

Below the state tree. Each row is a value that failed a guard, with the reason
it failed.

**This is a feature.** The alternative to declining is guessing, and a guess
that lands in the wrong field is indistinguishable — to the user — from a
correct memory. A decline is the system saying *I did not store that, and here
is why*.

How to read a reason:

- [`unknown_key`](#decline.unknown_key) — nothing in the registry claims that
  name. Rephrase using a more common word, or it may belong as a
  [dynamic field](#concept.dynamic-field).
- [`rejected_value`](#decline.rejected_value) — the field exists but the value
  is the wrong kind. This is the guard doing exactly its job.
- [`low_confidence`](#decline.low_confidence) — the tier that proposed it was
  not sure enough for that field.
- [`not an assertion`](#decline.not_an_assertion) — the clause was a question or
  a negation, not a claim.

See [decline and _unmapped](#concept.decline).
