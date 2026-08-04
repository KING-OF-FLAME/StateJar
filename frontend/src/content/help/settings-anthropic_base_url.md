---
id: settings.anthropic_base_url
title: ANTHROPIC_BASE_URL
category: settings
updated_at: 2026-08-04
summary: Environment variable ANTHROPIC_BASE_URL. Default: https://api.anthropic.com/v1
keywords: anthropic base url endpoint
---

**Environment variable:** `ANTHROPIC_BASE_URL`

**Default:** `https://api.anthropic.com/v1`


Where Anthropic requests are sent.

Change it to route through a gateway, a regional endpoint, or a proxy that
speaks the Anthropic API. StateJar appends its own paths to this base, so give
the API root and not a full endpoint URL.

See [Anthropic](#provider.anthropic).
