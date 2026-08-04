---
id: ui.tab_retrieved_context
title: Retrieved Context tab
category: interface
updated_at: 2026-08-04
summary: The exact subset sent to the model for the last question.
keywords: retrieved context subset disclosed sent minimal
---

Not your state — the slice of it that was disclosed for the most recent query,
plus how many fields were dropped and why the selector chose these.

This is the tab that makes minimal disclosure checkable. If your state has
twelve fields and this shows two, then ten were withheld, and the
[audit entry](#concept.audit-entry) records the same two keys.

Open it after any question where you want to know what the model was actually
told.
