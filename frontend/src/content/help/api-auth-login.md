---
id: api.auth.login
title: Log in
category: api
updated_at: 2026-08-04
summary: Exchange email and password for a bearer token.
keywords: login signin token bearer auth
---

`POST /api/v1/auth/login`


Returns an access token signed with [`JWT_SECRET`](#settings.jwt_secret). Send
it as `Authorization: Bearer <token>` on every other call.

For server-to-server use, prefer a StateJar API key from
[`/apikeys/generate`](#api.apikeys.generate) — it does not expire on a token
rotation and can be revoked individually.


Request and response shapes, with copyable samples in four languages, are in the [API Docs](/api-docs) — this entry explains the reasoning, not the schema.
