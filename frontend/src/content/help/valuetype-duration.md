---
id: valuetype.duration
title: Value type: Duration
category: reference
updated_at: 2026-08-04
summary: A length of time.
keywords: duration time hours days weeks length how long
---

**What it is.** A length of time.

**Examples.** `14 hours`, `two weeks`, `45 minutes`, `6 months`

**How StateJar treats it.** Distinct from a [date](#valuetype.date): a duration is how long, a date is when. Mixing them is a common failure — `push it by two weeks` is a duration operating on a date.

A field declares which value types it accepts. A value of the wrong type is [declined](#decline.rejected_value) rather than coerced. See [value type](#concept.value-type).
