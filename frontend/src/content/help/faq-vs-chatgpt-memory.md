---
id: faq.vs-chatgpt-memory
title: How is this different from ChatGPT memory?
category: faq
updated_at: 2026-08-04
summary: How is this different from built-in model memory?
keywords: chatgpt memory built in vendor compare difference openai
---

Three differences that matter, and one honest point in their favour.

**Portability.** Built-in memory belongs to that vendor's product. StateJar
state is addressed by a [handle](#concept.handle) that resolves the same
anywhere — a different session, a different model, a different vendor.

**Inspectability.** You can see every field StateJar holds, when it changed,
what it changed from, and exactly what was sent to the model on any given turn.

**Declining.** StateJar tells you when it did *not* store something, and why.
This is the part that has no equivalent: a memory feature that silently
remembers a number wrongly is indistinguishable, to the user, from one that
remembered it correctly.

**In their favour:** built-in memory requires no integration at all, and it
captures nuance — tone, preferences implied rather than stated — that a
type-checked field cannot represent. If you want a model that remembers you
found something funny, that is not what StateJar is.
