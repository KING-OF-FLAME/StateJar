---
id: valuetype.unknown
title: Value type: Unknown
category: reference
updated_at: 2026-08-04
summary: The classifier could not tell what kind of value this is.
keywords: unknown unclassified ambiguous fail closed
---

**What it is.** The classifier could not tell what kind of value this is.

**Examples.** an ambiguous fragment with no clarifying context

**How StateJar treats it.** **Fail-closed.** An unknown type is not assumed compatible with anything; it is refused by any field that demands a specific type, and the refusal shows as [`rejected_value`](#decline.rejected_value). Guessing here is exactly the failure mode StateJar exists to avoid.

A field declares which value types it accepts. A value of the wrong type is [declined](#decline.rejected_value) rather than coerced. See [value type](#concept.value-type).
