---
id: concept.qualifier
title: Qualifier
category: concepts
updated_at: 2026-08-04
summary: The part of a concept that says which end, which side, or which bound.
keywords: qualifier start end min max per total modifier
---

**Definition.** A modifier attached to a concept that distinguishes one variant from another: start, end, min, max, per, total.

**Why it exists.** 'Push the end date' has to find the end date, not the start date. Without a qualifier the update lands on whichever date field the matcher happened to like.

**Where you see it.** In path names — `constraints.budget.max`, `dynamic.delivery_window.start`.

**Worked example.** `Booking starts March 3 and ends March 9` creates two fields with `start` and `end` qualifiers. `Push the end to March 11` then updates only the second.

**Common misunderstanding.** That a qualifier is decoration. It is part of the identity of the field: a fact qualified `start` will not be written into a field whose path implies `end`, and the mismatch causes a decline rather than an overwrite.
