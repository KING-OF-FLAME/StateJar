---
id: concept.decline
title: Decline and _unmapped
category: concepts
updated_at: 2026-08-04
summary: A value StateJar refused to store, kept with the reason it was refused.
keywords: declined unmapped rejected refused reason not stored
---

**Definition.** A value that failed a guard and was parked in the `_unmapped` section along with a reason code, rather than being stored or dropped.

**Why it exists.** Silently dropping a value and silently storing it in the wrong place fail the same way — the user cannot tell. A decline is visible and has a stated cause.

**Where you see it.** The declined list in the Memory State panel. See [the declined section](#ui.declined_section).

**Worked example.** A value the registry has no field for is declined with [`unknown_key`](#decline.unknown_key). A value a field's normalizer rejects is declined with [`rejected_value`](#decline.rejected_value).

**Common misunderstanding.** That a decline means StateJar is broken. It means a guard did its job. The reason tells you whether the fix is a rephrase, a new alias, or nothing at all.
