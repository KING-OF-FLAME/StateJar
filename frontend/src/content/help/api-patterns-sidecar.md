---
id: api.patterns.sidecar
title: Pattern 1: Sidecar
category: api
updated_at: 2026-08-04
summary: You keep your model call; StateJar supplies the memory subset beside it.
keywords: sidecar pattern integration alongside query ingest
---

**Choose this when** you already have a working model integration and you want
memory added without rewriting the call.

**How it works.** Before you call your model, ask StateJar what matters for
this turn. Build your prompt with the subset. After the turn, hand the user's
message to StateJar to remember.

```
POST /api/v1/memory/query   -> the minimal subset for this question
  (your own model call, your own prompt, your own SDK)
POST /api/v1/memory/ingest  -> remember what the user said
```

**Why it is the default recommendation.** Nothing about your model call
changes. Your prompts, your streaming, your tool use, your vendor — all
untouched. StateJar is a lookup you make, not a layer you route through.

**What you keep responsibility for.** Building the prompt, and calling
`/memory/audit/manual` if you want the disclosure in the trail — StateJar
cannot log a call it did not make.

Related: [query](#api.memory.query), [ingest](#api.memory.ingest),
[manual audit](#api.audit.manual).
