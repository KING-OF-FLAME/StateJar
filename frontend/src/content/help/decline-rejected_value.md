---
id: decline.rejected_value
title: Declined: rejected_value
category: reference
updated_at: 2026-08-04
summary: The field exists, but the value is the wrong kind of thing.
keywords: rejected value declined type mismatch normalizer guard
---

**What it means.** The destination resolved fine and the value failed its
normalizer — the field would not accept that kind of value.

**This is the guard the whole product is built around.** A shipping assistant
told `max load per container is 24 tonnes` must not store a budget of
twenty-four rupees. It gets this reason instead.

**Why it happens.** A [value type](#concept.value-type) mismatch: a quantity
aimed at a money field, a duration aimed at a date, a value the normalizer
could not parse at all.

**What to do.** Check whether the value belongs in that field. If it does,
state it in the field's expected form (a date as a date, money with a
currency). If it does not, this decline just saved you a wrong memory.

**What it does not mean.** That StateJar failed. Silently coercing it would
have been the failure.
