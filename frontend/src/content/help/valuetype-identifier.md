---
id: valuetype.identifier
title: Value type: Identifier
category: reference
updated_at: 2026-08-04
summary: A code that names something rather than measuring it.
keywords: identifier id code reference number order pnr
---

**What it is.** A code that names something rather than measuring it.

**Examples.** `ORD-4471`, `PNR 8823`, `GSTIN 27AAAPA…`

**How StateJar treats it.** Identifiers look like numbers and are not. `4471` in `order 4471` must never be arithmetic, a budget, or a count — this type is what prevents that.

A field declares which value types it accepts. A value of the wrong type is [declined](#decline.rejected_value) rather than coerced. See [value type](#concept.value-type).
