---
id: faq.negative-savings
title: Why is my token savings negative?
category: faq
updated_at: 2026-08-04
summary: Why is my token savings negative?
keywords: negative savings tokens more expensive baseline demo
---

Only one of the two figures can go negative, so first check which you are
looking at.

**The savings badge and the Dashboard card cannot.** They measure against the
disclosable state and are clamped at zero.

**The 17-turn demo can**, because it measures against a **full-transcript
replay** — and early in a conversation, replaying three short messages is
genuinely cheaper than sending a state plus its scaffolding. The demo shows
those turns rather than starting the chart where it looks good.

It crosses over as the conversation grows, because the transcript grows without
bound and the state does not. See
[token savings and its baseline](#concept.token-savings).
