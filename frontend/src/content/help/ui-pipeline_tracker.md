---
id: ui.pipeline_tracker
title: The seven-stage pipeline tracker
category: interface
updated_at: 2026-08-04
summary: A live trace of the seven stages, with a real sublabel on each.
keywords: pipeline stages tracker seven ingest extract canonicalize handle store retrieve audit
---

The strip above the chat shows the seven stages a message passes through.
Nothing here runs on a timer of its own — every badge is filled from an actual
API response, so the strip cannot claim a stage the panels did not reach. The
only timed part is the reveal stagger, which paces stages that all completed in
one round trip so the eye can follow them.

| Stage | Sublabel | Means |
|---|---|---|
| **Ingest** | `sent` | the message reached the API |
| **Extract** | `N fields` | how many fields the tiers produced |
| **Canonicalize** | `sorted` | keys sorted at every level, the exact bytes the handle is computed from |
| **Handle** | first 8 hex characters | the content address that was derived |
| **Store** | `v1` or `v+1` | a first state, or a new version of an existing chain |
| **Retrieve** | `N of M fields` | how many of the eligible fields were disclosed |
| **Audit** | `logged` | a disclosure row was written |

Click any stage to see its payload — including the canonical string the handle
was actually computed from.

Retrieve and Audit only light up on a turn that asked something. An ingest-only
turn legitimately stops at Store.
