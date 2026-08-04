---
id: trouble.restore-different-state
title: Handle restore returns different state
category: troubleshooting
updated_at: 2026-08-04
summary: You restored a handle and the state is not what you expected.
keywords: restore wrong state handle mismatch different unexpected
---

**Symptom.** You restored a handle and the state is not what you expected.

**Likely cause.** Almost always one of three things:

- **The handle is from a different session or account.** Handles are scoped to
  your account; one from elsewhere will not resolve.
- **You copied a truncated handle.** The display shortens it in some places.
  Use the copy button, which copies the full value.
- **You are looking at the right state and misremembering the wrong one.** The
  Handles tab lists every version — inspect a few and find the one you meant.

What it is *not*: silent corruption. Restore re-derives the handle from the
stored state and refuses if they disagree, so a restore that succeeded returned
exactly the bytes that hashed to that handle.

**Fix.** Copy the handle again with the copy button, and check the
[Handles tab](#ui.tab_handles) for the version you actually want. See
[restore](#api.memory.restore).
