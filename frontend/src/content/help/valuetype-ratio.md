---
id: valuetype.ratio
title: Value type: Ratio
category: reference
updated_at: 2026-08-04
summary: A relationship between two numbers.
keywords: ratio proportion odds pair to one
---

**What it is.** A relationship between two numbers.

**Examples.** `3:1`, `2 to 1`, `one in four`

**How StateJar treats it.** A ratio is a pair, not a number. Storing `3:1` as `3` would lose exactly the part that carries the meaning.

A field declares which value types it accepts. A value of the wrong type is [declined](#decline.rejected_value) rather than coerced. See [value type](#concept.value-type).
