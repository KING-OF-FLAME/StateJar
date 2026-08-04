---
id: gs.reading-memory-state
title: Reading the Memory State panel
category: getting-started
updated_at: 2026-08-04
summary: What the sections mean, what the colours mean, and why an empty panel is sometimes correct.
keywords: memory state panel read sections facts constraints dynamic
---

The Memory State tab shows every namespace the API returns, in this order:

- **facts** — things that are true about you or the situation: a name, a city.
- **preferences** — how you want things done: contact mode, a colour.
- **constraints** — limits: a budget, a deadline, a headcount.
- **decisions** — choices already made.
- **goals** — what you are trying to achieve.
- **dynamic** — concepts nobody wrote a schema for. A kiln schedule, a load
  limit per container, a hive inspection interval. See
  [dynamic fields](#concept.dynamic-field).
- **_unmapped** — values that were **declined**, each with a reason. See
  [the declined section](#ui.declined_section).
- **conflicts**, **history**, **retractions** — the audit trail of changes.

A value renders as its normalized form, so `{"currency": "INR", "value": 5000}`
is what was actually stored, not the words you typed.

**Fields highlighted after a turn** are the ones that turn changed.

**An empty panel after a message is a real answer**, not a bug. If you said
"that sounds good, let's do it" there is nothing in it to store. If you said
something with a value in it and the panel is still empty, check `_unmapped` —
it was probably declined, and the reason will say why.
