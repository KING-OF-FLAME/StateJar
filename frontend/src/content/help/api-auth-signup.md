---
id: api.auth.signup
title: Create an account
category: api
updated_at: 2026-08-04
summary: Create a StateJar account with an email and a password.
keywords: signup register account create user
---

`POST /api/v1/auth/signup`


Returns the created user. Passwords are hashed with bcrypt before storage.

An account is the **namespace**: everything you store lives under it, and no
credential can address another account's memory. See [scope](#concept.scope).


Request and response shapes, with copyable samples in four languages, are in the [API Docs](/api-docs) — this entry explains the reasoning, not the schema.
