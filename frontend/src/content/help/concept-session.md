---
id: concept.session
title: Session
category: concepts
updated_at: 2026-08-04
summary: A named conversation thread. State is scoped to it unless you move a handle across.
keywords: session thread conversation scope isolate
---

**Definition.** A named thread of conversation. Every state StateJar writes is tagged with the session it came from.

**Why it exists.** Two conversations about different things should not contaminate each other. Planning a wedding and filing an insurance claim both have a budget, and they are not the same budget.

**Where you see it.** The dropdown in the Playground toolbar. `+ New session` makes another one. See [the session selector](#ui.session_selector).

**Worked example.** Send `my budget is 5000` in session-1, then switch to session-2 and open Memory State. It is empty. Switch back and the 5000 is still there.

**Common misunderstanding.** That a session holds your chat. It does not — the server stores state, never the transcript. The words are kept by your browser, which is why history is per device. See [the FAQ](#faq.transcript-storage).
