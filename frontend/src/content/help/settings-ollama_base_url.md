---
id: settings.ollama_base_url
title: OLLAMA_BASE_URL
category: settings
updated_at: 2026-08-04
summary: Environment variable OLLAMA_BASE_URL. Default: http://localhost:11434
keywords: ollama base url localhost 11434
---

**Environment variable:** `OLLAMA_BASE_URL`

**Default:** `http://localhost:11434`


The default address offered for a local Ollama daemon.

This is a *default for the form*, not a route the server uses: for a local
daemon the browser talks to Ollama directly, because a hosted backend cannot
reach an address on your machine. See [Ollama local](#provider.ollama).

A base carrying a trailing `/api` or `/v1` is normalised back to the host, so
pasting a URL straight from Ollama's docs works.
