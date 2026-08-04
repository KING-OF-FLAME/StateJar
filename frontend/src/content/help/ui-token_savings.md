---
id: ui.token_savings
title: Token savings badge
category: interface
updated_at: 2026-08-04
summary: How much smaller the disclosed subset was, against a stated baseline.
keywords: tokens saved badge percentage savings cost
---

Appears after a question. It reports how much smaller what was sent was than
the **disclosable state** — every field that was eligible to be disclosed.

Two consequences of that baseline, both deliberate:

- It **cannot go negative**. It is clamped at zero.
- It is **not** a comparison against replaying the conversation. The 17-turn
  relief demo makes that other comparison, and that one *can* go negative and
  says so on screen.

A small number early on is honest, not broken: with three fields stored, there
is not much to withhold. Read
[token savings and its baseline](#concept.token-savings) before quoting any
figure from here.
