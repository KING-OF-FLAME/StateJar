---
id: trouble.value-not-stored
title: A value you stated was not stored
category: troubleshooting
updated_at: 2026-08-04
summary: You said something with a number in it and the Memory State panel does not show it.
keywords: not stored missing value declined nothing extracted
---

**Symptom.** You said something with a number in it and the Memory State panel does not show it.

**Likely cause.** Three possibilities, and the panel tells you which:

1. It was **declined**. Look at the declined section — there will be a row with
   a [reason](#ui.declined_section).
2. It was **unresolved** — you named a field without giving a value, or hedged.
   See [not provided](#decline.not_provided) and
   [user unsure](#decline.user_unsure).
3. It was **not an assertion** — a question or a negation. See
   [that reason](#decline.not_an_assertion).

If none of those appear, no tier recognised anything to extract.

**Fix.** Read the decline reason first; it names the fix. If nothing was extracted
at all, restate it as a plain assertion with the value attached to its concept
— `family kit weight is 12 kg` rather than `the kits, they're about 12 kilos I
think`. If the concept is genuinely novel, it should land as a
[dynamic field](#concept.dynamic-field); if it does not, that is worth
reporting.
