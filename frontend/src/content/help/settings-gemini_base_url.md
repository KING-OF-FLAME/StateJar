---
id: settings.gemini_base_url
title: GEMINI_BASE_URL
category: settings
updated_at: 2026-08-04
summary: Environment variable GEMINI_BASE_URL. Default: https://generativelanguage.googleapis.com/v1beta
keywords: gemini google base url endpoint
---

**Environment variable:** `GEMINI_BASE_URL`

**Default:** `https://generativelanguage.googleapis.com/v1beta`


Where Google Gemini requests are sent.

The default is the `v1beta` surface, which is where the current Gemini models
live. Change it for Vertex AI or a proxy. Give the API root; StateJar appends
its own paths.

See [Google](#provider.gemini).
