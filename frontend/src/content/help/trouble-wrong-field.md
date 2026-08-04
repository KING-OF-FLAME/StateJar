---
id: trouble.wrong-field
title: A value stored under an unexpected field
category: troubleshooting
updated_at: 2026-08-04
summary: The value is there, but under a field name you did not expect.
keywords: wrong field misrouted budget default alias unexpected
---

**Symptom.** The value is there, but under a field name you did not expect.

**Likely cause.** Either it resolved through an alias to a
[canonical path](#concept.canonical-path) — which is correct, and is what stops
the same number being stored three times under three phrasings — or it fell
through to a default destination.

**A known case:** a money value in a clause that names no recognised money
concept currently defaults to `constraints.budget.max`. The vocabulary is
literal, not stemmed, so `cost` is recognised and `costs` is not. See
`docs/known-issues.md`.

**Fix.** If it is an alias resolution, nothing is wrong — check the value is
right. If it is the money default, restate using a word the vocabulary knows
(`budget`, `cost`, `price`, `spend`) or one that clearly names a different
concept (`invoice`, `rent`, `freight`), which keeps it in its own field.
