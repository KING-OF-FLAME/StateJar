---
id: ui.tab_memory_state
title: Memory State tab
category: interface
updated_at: 2026-08-04
summary: Everything currently remembered, by namespace.
keywords: memory state tab tree fields current
---

The active state, rendered as a tree. Fields changed by the last turn are
highlighted, and hovering a field shows which [tier](#concept.extraction-tier)
produced it.

Every namespace the API returns is rendered — including `dynamic`, which is
where concepts nobody wrote a schema for live. See
[reading the Memory State panel](#gs.reading-memory-state) and
[dynamic fields](#concept.dynamic-field).

Below the tree sits the [declined section](#ui.declined_section), which is
where to look when something you said is not in the tree.
