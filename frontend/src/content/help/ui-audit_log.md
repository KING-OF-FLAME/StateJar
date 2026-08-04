---
id: ui.audit_log
title: Audit Log screen
category: interface
updated_at: 2026-08-04
summary: Every disclosure across every session, filterable, with replay.
keywords: audit log history disclosures replay filter
---

The account-wide version of the Playground's Audit tab. Each row is one
disclosure: when, which handle, which fields, which provider and model.

**Replay** reconstructs exactly what was sent for that request by re-reading
the handle and re-applying the recorded field keys. If the state behind the
handle had been altered, the re-derived handle would not match and the replay
says so — which is what makes the audit trail evidence rather than a log.

No message text is stored here, only field keys. See
[audit entry](#concept.audit-entry) and [the replay endpoint](#api.audit.replay).
