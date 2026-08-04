---
id: decline.low_confidence
title: Declined: low_confidence
category: reference
updated_at: 2026-08-04
summary: The tier that proposed it was not sure enough for that field.
keywords: low confidence declined threshold uncertain
---

**What it means.** A field can require a minimum confidence. The tier that
proposed this value scored below it, so it was declined rather than stored.

**Why it happens.** [GLiNER2](#tier.gliner2) carries 0.55 and
[tier 3](#tier.llm) carries 0.5. A field that demands more than that will
refuse both and accept only a [rules](#tier.rules) match, which carries 1.0.

**What to do.** State the value more directly, in a form the deterministic tier
can match. `My budget is 5000 rupees` rather than a value buried in a clause.

**What it does not mean.** That the value was wrong — only that the system's
own estimate of its reliability did not clear the bar this field sets.
