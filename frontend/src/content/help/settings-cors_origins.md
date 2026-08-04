---
id: settings.cors_origins
title: CORS_ORIGINS
category: settings
updated_at: 2026-08-04
summary: Environment variable CORS_ORIGINS. Default: localhost:5173, statejar.vercel.app, statejar.com
keywords: cors origins browser deploy allowed
---

**Environment variable:** `CORS_ORIGINS`

**Default:** `localhost:5173, statejar.vercel.app, statejar.com`


Which browser origins may call the API.

A frontend served from an origin not in this list gets a CORS failure that
looks, from the browser, like the API being down. When you deploy the frontend
somewhere new, add its origin here.

This is deployment wiring rather than a product feature — see
`docs/deployment.md`.
