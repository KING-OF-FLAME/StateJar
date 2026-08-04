---
id: settings.retriever_full_state_tokens
title: RETRIEVER_FULL_STATE_TOKENS
category: settings
updated_at: 2026-08-04
summary: Environment variable RETRIEVER_FULL_STATE_TOKENS. Default: 800
keywords: retrieval full state tokens threshold budget
---

**Environment variable:** `RETRIEVER_FULL_STATE_TOKENS`

**Default:** `800`


The size below which retrieval may disclose the whole state rather than a
subset.

Minimal disclosure has overhead — selection, plus the scaffolding around a
subset. Under a certain size that overhead exceeds what withholding saves, and
sending everything is both cheaper and more useful.

Raising it discloses more per call. Lowering it discloses less and pays the
selection cost more often. 800 tokens is roughly a small state with a dozen
fields.
