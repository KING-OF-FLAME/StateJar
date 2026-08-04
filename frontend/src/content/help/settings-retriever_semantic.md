---
id: settings.retriever_semantic
title: RETRIEVER_SEMANTIC
category: settings
updated_at: 2026-08-04
summary: Environment variable RETRIEVER_SEMANTIC. Default: False
keywords: semantic retrieval embedding fallback search
---

**Environment variable:** `RETRIEVER_SEMANTIC`

**Default:** `False`


Whether retrieval may use a semantic fallback when keyword selection finds
nothing.

**Read this before enabling it.** The guarantee it is written against is that
handles are byte-identical with semantic retrieval on or off: retrieval is a
*read* path, and the write path — extraction, canonicalization, hashing — is
untouched by it. A test asserts exactly that.

So this can change *what a model is told* for a given question. It can never
change what is stored or what a state hashes to.
