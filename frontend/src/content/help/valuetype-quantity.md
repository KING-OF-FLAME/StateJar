---
id: valuetype.quantity
title: Value type: Quantity
category: reference
updated_at: 2026-08-04
summary: A number with a unit of measure.
keywords: quantity unit measure weight length volume kg tonnes
---

**What it is.** A number with a unit of measure.

**Examples.** `24 tonnes`, `1,240 kg`, `500 ml`, `3.2 km`

**How StateJar treats it.** Normalized to a base unit, so `1,240 kg` and `1.24 tonnes` are the same stored value and produce the same handle. Weight, length, volume and data units are recognised.

A field declares which value types it accepts. A value of the wrong type is [declined](#decline.rejected_value) rather than coerced. See [value type](#concept.value-type).
