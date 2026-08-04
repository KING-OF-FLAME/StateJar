---
id: concept.conflict
title: Conflict
category: concepts
updated_at: 2026-08-04
summary: Two values asserted for one field, recorded rather than silently resolved.
keywords: conflict contradiction disagreement two values
---

**Definition.** A record that two values were asserted for the same concept in a way that does not read as a straightforward replacement.

**Why it exists.** Some contradictions are not corrections. 'Call me instead of emailing' rejects one option and picks another, and that is worth recording rather than flattening.

**Where you see it.** The `conflicts` list in Memory State.

**Worked example.** `Email me` then `actually call me instead` records a conflict on `contact_mode` with the reason `user rejected email in favour of phone`. See [that reason](#decline.user_rejected).

**Common misunderstanding.** That a conflict means the state is inconsistent. The state is never inconsistent — the field holds exactly one value. The conflict is a note about how it got there.
