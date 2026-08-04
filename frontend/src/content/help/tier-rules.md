---
id: tier.rules
title: Tier 1: rules
category: reference
updated_at: 2026-08-04
summary: Deterministic patterns. Free, exact, narrow, identical on every machine.
keywords: rules tier1 deterministic patterns regex
---

**What it is.** Hand-written patterns and a canonical alias registry. No model,
no network, no randomness.

**What it catches.** Direct statements — `my budget is 5000`,
`the deadline is March 3`, `each firing takes 14 hours` — plus generic
assignments (`bedrooms: 3`) and open concepts nobody wrote a rule for.

**Why it runs first.** It costs nothing and it is reproducible. The same
message on two machines produces the same fields, which is what lets a handle
mean anything.

**Confidence.** 1.0. A rule match is treated as certain, because it matched a
literal pattern rather than judging.

**When you see it alone.** Most of the time, on well-formed input. A single
`rules` [chip](#ui.tier_chips) is the normal, cheap, good case — not a sign
that something was skipped.
