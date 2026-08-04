---
id: ui.handle_display
title: The handle line and copy button
category: interface
updated_at: 2026-08-04
summary: The address of the state you are looking at.
keywords: handle copy button address hash shm clipboard
---

Sits under the tier chips: `handle: shm_…` with a copy button.

The handle is the [content address](#concept.handle) of the current state. It
changes whenever the state changes and is identical whenever the state is
identical.

Copy it to move this exact memory somewhere else — another session, another
model, another vendor. Paste it into [restore](#ui.restore_handle).

It is safe to share in the sense that it is a hash, but it is a *key* to your
state: anyone who can call your account's API with it can read that state.
