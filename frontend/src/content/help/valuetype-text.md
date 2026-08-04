---
id: valuetype.text
title: Value type: Text
category: reference
updated_at: 2026-08-04
summary: A value that is words rather than a measurement.
keywords: text string words name city label free
---

**What it is.** A value that is words rather than a measurement.

**Examples.** a name, a city, a colour, a chosen option

**How StateJar treats it.** Text fields carry their own guards — a blocklist stops filler words being stored as someone's name, and degenerate values are rejected rather than kept.

A field declares which value types it accepts. A value of the wrong type is [declined](#decline.rejected_value) rather than coerced. See [value type](#concept.value-type).
