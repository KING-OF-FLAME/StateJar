---
id: ui.session_selector
title: Session selector and + New session
category: interface
updated_at: 2026-08-04
summary: Pick a thread, or start an isolated one.
keywords: session selector switch new thread dropdown
---

The dropdown lists your sessions; **+ New session** adds one.

Switching swaps everything belonging to that session together: the transcript,
the [tier chips](#ui.tier_chips), the per-field origins, the
[pipeline tracker](#ui.pipeline_tracker), the last retrieval and the memory
state. Nothing from the session you left stays on screen — showing the previous
session's run beside this session's messages would be worse than showing
nothing.

The session you were last in is remembered, so a reload returns you there
rather than to the first session in the list.

To carry memory across sessions deliberately, copy a handle and
[restore it](#ui.restore_handle). See [session](#concept.session).
