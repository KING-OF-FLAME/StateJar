---
id: concept.normalization
title: Normalization and base units
category: concepts
updated_at: 2026-08-04
summary: Equivalent values are stored identically, so the handle does not depend on phrasing.
keywords: normalize base unit convert iso currency equivalent
---

**Definition.** Converting a value to one canonical form before storing it: a currency and an amount, a date as ISO, a measure in its base unit.

**Why it exists.** Two ways of writing the same thing must produce the same bytes, or the handle would depend on wording rather than meaning.

**Where you see it.** In the rendered value in Memory State, which shows the stored form rather than your words.

**Worked example.** `1,240 kg` and `1.24 tonnes` both normalize to 1240000 grams. Both produce the same field value and therefore the same handle.

**Common misunderstanding.** That normalization loses your original phrasing. The raw text is kept alongside the normalized value for display; it is the normalized form that is compared and hashed.
