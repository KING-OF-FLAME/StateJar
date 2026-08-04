---
id: demo.markers
title: The 17-turn demo: what each marked turn shows
category: demo
updated_at: 2026-08-04
summary: Three turns are marked because they demonstrate the behaviours people doubt.
keywords: demo markers update retracted corrected turns
---

Three of the seventeen turns carry a marker. They are the ones worth watching.

**`update` — turn 8.** *"Update: truck count is now 5."* The truck count was 3.
It becomes 5, the 3 moves to history, and the handle changes because the state
changed. Watch the Memory State panel: there is **one** truck count, not two.
See [supersession](#concept.supersession).

**`retracted` — turn 11.** *"Actually cancel the purification tablets, state
supply already covered it."* The tablets field is not overwritten with zero and
not left stale — it is removed. The active state no longer has it. See
[retraction](#concept.retraction).

**`corrected` — turn 13.** *"Correction: budget is now ₹22 lakh."* The budget
was ₹18 lakh. This matters for the payoff: the final answer uses ₹22 lakh, and
that is only right because the ₹18 lakh was superseded rather than kept
alongside it.

**The payoff — turn 17.** The kit count is computed from the corrected budget
and the kit price, two facts stated eleven turns apart, with the retracted item
correctly absent.
