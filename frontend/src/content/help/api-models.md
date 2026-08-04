---
id: api.models
title: Model catalog
category: api
updated_at: 2026-08-04
summary: Which models are available to you, grouped by provider.
keywords: models catalog list available providers
---

`GET /api/v1/models`


Only providers you have configured appear, with free and paid models listed
separately where a provider offers both.

**Local Ollama models are not in here.** A hosted backend cannot see
`http://localhost:11434`; the browser enumerates those itself. See
[the model selector](#ui.model_selector).


Request and response shapes, with copyable samples in four languages, are in the [API Docs](/api-docs) — this entry explains the reasoning, not the schema.
