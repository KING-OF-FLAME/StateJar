---
id: concept.audit-entry
title: Audit entry
category: concepts
updated_at: 2026-08-04
summary: One row per disclosure: what was sent, from which handle, to which model.
keywords: audit log disclosure trail record evidence
---

**Definition.** A record written every time state is disclosed to a model: the handle used, the exact field keys sent, the provider, the model, and a request id.

**Why it exists.** 'Minimal disclosure' is a claim that has to be checkable. The audit entry is the evidence, and the replay endpoint reconstructs the exact subset from the handle.

**Where you see it.** The Audit tab in the Playground, the Audit Log screen, and `GET /audit`.

**Worked example.** Ask a question and open the Audit tab. One row appears listing the disclosed keys — typically two or three, not your whole state.

**Common misunderstanding.** That the audit log stores the conversation. It stores field *keys*, never field values and never message text. See [the replay endpoint](#api.audit.replay).
