---
id: ui.api_keys
title: API Keys screen
category: interface
updated_at: 2026-08-04
summary: Provider keys in, StateJar keys out.
keywords: api keys provider credentials tokens secrets
---

Two independent halves.

**Provider keys** — one card per provider you can connect
([OpenRouter](#provider.openrouter), [OpenAI](#provider.openai),
[Anthropic](#provider.anthropic), [Google](#provider.gemini),
[Ollama local](#provider.ollama), [Ollama remote](#provider.ollama_remote)).
Paste a key, press Save, then **Test connection** to confirm it actually works
before you need it in front of an audience. Keys are encrypted at rest and are
never returned by the API — the list shows only the last four characters.

**StateJar API keys** — keys *you* generate to call StateJar from your own
code. Generated keys are shown once, at creation. There is no way to retrieve
one later; generate a new key and delete the old one.

Related endpoints: [provider keys](#api.keys.provider),
[connection test](#api.keys.provider.test), [your API keys](#api.apikeys).
