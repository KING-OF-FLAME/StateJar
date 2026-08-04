---
id: concept.canonical-path
title: Canonical path
category: concepts
updated_at: 2026-08-04
summary: The one dotted address a concept resolves to, no matter how you phrase it.
keywords: canonical path registry alias dotted route
---

**Definition.** The single dotted address a concept resolves to, such as `constraints.budget.max`. Aliases map onto it; it never maps onto anything else.

**Why it exists.** Without it, `budget`, `max budget` and `spending limit` would each create a field, and the state would hold three answers to one question.

**Where you see it.** As the key path in Memory State, and in the `field` column of a change acknowledgement.

**Worked example.** `budget`, `max budget`, `budget limit` and `spending cap` all canonicalize to `constraints.budget.max`. Only one field is ever written.

**Common misunderstanding.** That the path is chosen per message. It is fixed in the registry, which is checked at the storage boundary — two aliases resolving to the same path is an assertion failure, not a merge.
