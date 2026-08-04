---
id: concept.field
title: Field
category: concepts
updated_at: 2026-08-04
summary: One named slot holding one value, in one section.
keywords: field slot value name path
---

**Definition.** One named slot in the state that holds exactly one value, living in one of the sections (facts, preferences, constraints, decisions, goals, dynamic).

**Why it exists.** Contradiction is prevented structurally. If a concept has exactly one home, two values for it cannot both be current — one must supersede the other.

**Where you see it.** Every leaf in the Memory State tree is a field.

**Worked example.** `constraints.budget.max` is a field. So is `facts.name`. So is `dynamic.load_limit_per_container` once you mention one.

**Common misunderstanding.** That similar names are different fields. `budget`, `my budget`, and `the budget` all resolve to the same field through the alias registry — that is what stops the same number being stored three times.
