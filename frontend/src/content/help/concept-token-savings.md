---
id: concept.token-savings
title: Token savings and its baseline
category: concepts
updated_at: 2026-08-04
summary: Two different baselines ship, they answer different questions, and a percentage without its baseline means nothing.
keywords: tokens savings cost baseline percentage cheaper negative
---

**Definition.** How much smaller what was actually sent to the model is than
what would have been sent without minimal disclosure.

**Why it exists.** The claim being made is that disclosing a subset is cheaper
than the alternative. A percentage with no stated baseline is not a claim, it
is a decoration.

**Where you see it.** Two places, and **they use different baselines**. This is
the most misread number in the product, so it is worth being exact.

| Where | Baseline | Can it go negative? |
|---|---|---|
| Query savings badge, and the Dashboard's *Tokens saved (last chat)* | the **disclosable state** — every field that was eligible to be sent | No. It is clamped at 0. |
| The 17-turn relief demo | a **full-transcript replay** — every message so far, resent | Yes, and it is early on. |

The first answers *"of what I could have disclosed, how little did I?"* — it
measures the retriever. The second answers *"against a system with no memory
layer, am I ahead?"* — it measures the product. Both are honest; they are not
interchangeable, and neither one is "the real number".

**Worked example.** Ask one question of a ten-field state and the badge may say
80% — two fields sent out of ten eligible. On turn two of the demo the same
mechanism shows *more* than replay, because two short messages are cheaper to
resend than a state plus its scaffolding. The demo says so on screen rather
than hiding the turns where it loses.

**Common misunderstanding.** That the baseline is "sending nothing". It never
is. Compared to sending nothing, any disclosure costs more; the question is
always *cheaper than what*.

Related: [the savings badge](#ui.token_savings), [the Dashboard](#ui.dashboard).
