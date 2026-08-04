---
id: valuetype.count
title: Value type: Count
category: reference
updated_at: 2026-08-04
summary: A plain number of countable things.
keywords: count number how many quantity plain integer
---

**What it is.** A plain number of countable things.

**Examples.** `40 volunteers`, `3 bedrooms`, `12 crates`

**How StateJar treats it.** A count has a countable noun but no unit of measure — that is what separates it from a [quantity](#valuetype.quantity).

A field declares which value types it accepts. A value of the wrong type is [declined](#decline.rejected_value) rather than coerced. See [value type](#concept.value-type).
