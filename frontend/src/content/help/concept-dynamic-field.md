---
id: concept.dynamic-field
title: Dynamic field
category: concepts
updated_at: 2026-08-04
summary: A field for a concept nobody wrote a schema for. First-class, not a leftover.
keywords: dynamic unknown field custom concept open extraction schema-free
---

**Definition.** A field created for a concept the registry has no entry for, stored under `dynamic` with a slug derived from what you called it.

**Why it exists.** StateJar has never been taught what a kiln schedule or a freight manifest looks like. Without dynamic fields, everything outside a fixed schema would be lost — and it was, before they existed.

**Where you see it.** The `dynamic` section of Memory State.

**Worked example.** `Each kiln firing takes 14 hours` creates `dynamic.kiln_firing` holding a duration of 14 hours. No rule for kilns exists anywhere in the code.

**Common misunderstanding.** That dynamic fields are second-class or temporary. They are hashed into the handle exactly like registry fields, which is why concept reuse has to be deterministic rather than similarity-based.
