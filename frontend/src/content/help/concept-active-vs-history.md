---
id: concept.active-vs-history
title: Active state vs history
category: concepts
updated_at: 2026-08-04
summary: The field holds one value; everything it used to hold is kept separately.
keywords: history active superseded previous old value version
---

**Definition.** The active state is what a field holds now. History is every value it previously held, kept in order and never shown to the model.

**Why it exists.** A model shown both the old and the new value will sometimes answer from the old one. Keeping them in separate places makes that impossible rather than unlikely.

**Where you see it.** Active values are the main tree in Memory State; superseded values appear under `history` and in the Handles tab as earlier versions.

**Worked example.** Say `budget is 5000`, then `actually 8000`. The active state has 8000. History records 5000. A question about the budget retrieves 8000 only.

**Common misunderstanding.** That history is a backup. It is a record. You cannot lose data by updating a field, but retrieval will never quietly serve you a historical value.
