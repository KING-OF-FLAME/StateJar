---
id: valuetype.percent
title: Value type: Percent
category: reference
updated_at: 2026-08-04
summary: A proportion out of a hundred.
keywords: percent percentage proportion rate
---

**What it is.** A proportion out of a hundred.

**Examples.** `20%`, `20 percent`

**How StateJar treats it.** Kept distinct from a plain [count](#valuetype.count) and from a [ratio](#valuetype.ratio). `20%` and `20` are not the same value and are not interchangeable in a field.

A field declares which value types it accepts. A value of the wrong type is [declined](#decline.rejected_value) rather than coerced. See [value type](#concept.value-type).
