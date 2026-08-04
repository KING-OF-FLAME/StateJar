---
id: demo.scenario
title: The 17-turn demo: the scenario
category: demo
updated_at: 2026-08-04
summary: A Wayanad relief operation, built one fact at a time over seventeen turns.
keywords: demo scenario relief wayanad 17 turn story
---

A coordinator running a disaster-relief operation in Wayanad district feeds
details in as they arrive: displaced families, truck capacity, convoy dates, a
coordinator's contact, a sanctioned budget, kit specifications, supplies,
staffing, freight costs.

Seventeen turns in, they ask a question that needs several of those facts at
once:

> How many family kits can we cover with the current budget?

The answer is computed from the **retrieved state alone**. The seventeen
messages that built it are never replayed.

**Why this scenario.** It is a setting where a silently misremembered number
does real harm, and where the facts are ordinary enough that no domain
knowledge could have been built in. There is no relief-operation schema
anywhere in StateJar.

**A note on phrasing.** Several turns are worded more like a form than a
sentence. The extractor is frozen, so where a natural phrasing did not survive
it the *turn* was rewritten rather than the pipeline. Those replacements have
not yet been re-measured with [tier 3](#tier.llm) live.

Run it from the Playground: **▶ Run 17-turn demo**. No provider key needed.
