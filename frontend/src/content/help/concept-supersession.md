---
id: concept.supersession
title: Supersession
category: concepts
updated_at: 2026-08-04
summary: A new value replaces the old one; the old one moves to history.
keywords: supersede replace update change overwrite
---

**Definition.** Replacing the current value of a field with a new one, moving the previous value into history and advancing the state version.

**Why it exists.** So that changing your mind produces one current answer rather than two competing ones.

**Where you see it.** As a change line after a turn (`budget: 5000 to 8000`), and as a new version in the Handles tab.

**Worked example.** `Budget is 5000` then `make it 8000`. The field now holds 8000, history holds 5000, and the handle is different because the state is.

**Common misunderstanding.** That supersession is the same as a conflict. Supersession is an orderly replacement. A [conflict](#concept.conflict) is recorded when two values are asserted without one clearly replacing the other.
