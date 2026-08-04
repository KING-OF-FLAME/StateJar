---
id: api.patterns.proxy
title: Pattern 2: Proxy
category: api
updated_at: 2026-08-04
summary: StateJar makes the model call for you and returns the reply.
keywords: proxy pattern chat integration passthrough
---

**Choose this when** you want the shortest path from zero to working memory,
and you are content for StateJar to hold the provider key and make the call.

**How it works.** One endpoint does everything: retrieve, prompt, call, audit,
reply.

```
POST /api/v1/chat  -> subset retrieved, model called, audit written, reply returned
```

**What it does not do**, stated plainly so you do not discover it later:

- **No streaming.** The reply is returned complete.
- **No tool or function calling.** The model is asked a question and answers.
- **No control over the prompt.** The prompt is built from the retrieved subset;
  you cannot inject a system prompt of your own through this path.
- **No vendor-specific parameters.** Anything outside model, message and key is
  not passed through.

If any of those matter, use the [sidecar](#api.patterns.sidecar).

Related: [chat](#api.chat).
