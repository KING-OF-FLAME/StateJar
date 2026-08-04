---
id: decline.unknown_key
title: Declined: unknown_key
category: reference
updated_at: 2026-08-04
summary: Nothing in the registry claims that field name.
keywords: unknown key declined unmapped registry alias
---

**What it means.** A value arrived addressed to a field name that no registry
entry and no alias resolves to.

**Why it happens.** Usually an extractor produced a key from your phrasing that
does not map onto a known concept.

**What to do.** Often nothing — if the concept is genuinely new it should have
become a [dynamic field](#concept.dynamic-field) instead, and seeing this
reason for something that clearly is a concept is worth reporting. Otherwise,
rephrase using a more common word for the same thing.

**What it does not mean.** That the value was wrong. The value was never
examined; only its destination failed.
