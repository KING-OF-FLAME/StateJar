---
id: ui.restore_handle
title: Restore a handle
category: interface
updated_at: 2026-08-04
summary: Adopt a previously sealed state into the current session.
keywords: restore handle paste adopt load cross session
---

The box in the Playground toolbar. Paste a handle, submit, and that state
becomes the current state of the session you are in.

Restore re-derives the handle from the stored state and refuses if the two do
not match, so a successful restore is a verification, not just a lookup.

This is how memory crosses a session boundary without a shared user id. See
[your first handle restore](#gs.first-handle-restore) and
[the endpoint](#api.memory.restore).

If a restore appears to return different state than you expected, see
[the troubleshooting entry](#trouble.restore-different-state).
