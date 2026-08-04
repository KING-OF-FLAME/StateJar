---
id: valuetype.date
title: Value type: Date
category: reference
updated_at: 2026-08-04
summary: A point in time.
keywords: date calendar deadline when day iso
---

**What it is.** A point in time.

**Examples.** `March 3`, `2026-03-03`, `next Friday`, `3rd March`

**How StateJar treats it.** Stored as ISO alongside the raw text you used, so display keeps your phrasing while comparison uses the normalized form. A date will not be accepted by a money or quantity field.

A field declares which value types it accepts. A value of the wrong type is [declined](#decline.rejected_value) rather than coerced. See [value type](#concept.value-type).
