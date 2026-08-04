---
id: valuetype.money
title: Value type: Money
category: reference
updated_at: 2026-08-04
summary: An amount with a currency.
keywords: money currency rupees dollars amount price
---

**What it is.** An amount with a currency.

**Examples.** `5000 rupees`, `INR 5,000`, `Rs 5000`, `$120`

**How StateJar treats it.** Requires a positive signal — a symbol, a currency word, or a money noun in the clause. **There is no default currency.** A bare number is not money, which is precisely what stops `24` in a load-limit clause becoming twenty-four rupees.

A field declares which value types it accepts. A value of the wrong type is [declined](#decline.rejected_value) rather than coerced. See [value type](#concept.value-type).
