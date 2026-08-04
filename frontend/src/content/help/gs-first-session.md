---
id: gs.first-session
title: Your first session
category: getting-started
updated_at: 2026-08-04
summary: Sign in, send one message, and read what the six panels tell you about it.
keywords: tutorial walkthrough first steps playground begin
---

1. **Sign in** and open **Playground** from the sidebar.
2. **Send a message with a fact in it.** Try:
   `My budget is 5000 rupees and the deadline is March 3.`
3. **Watch the pipeline strip** above the chat. Seven stages light up as the
   response comes back — that is a real trace, not an animation on a timer.
   See [the pipeline tracker](#ui.pipeline_tracker).
4. **Open the Memory State tab** on the right. You will see two fields:
   `constraints.budget.max` holding `{currency: "INR", value: 5000}` and
   `constraints.deadline` holding the date. Note that 5000 was stored as money
   *with a currency*, and March 3 as a date — not as the number 3.
5. **Look at the handle line** under the tabs. It reads something like
   `shm_a5f9911c29fa…`. That is the address of the state you just created.
6. **Send a second message** that changes something:
   `Actually the budget is 8000.` The budget field now holds 8000, the old
   value is in history, and the handle has changed — because the state did.

You do not need a provider key for steps 1–6: `/memory/ingest` runs the whole
memory pipeline on its own. A key is only needed to get a model's *reply*.

Next: [setting up a provider](#gs.provider-setup).
