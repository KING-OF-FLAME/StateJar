---
id: gs.provider-setup
title: Setting up a provider
category: getting-started
updated_at: 2026-08-04
summary: Add one key on the API Keys screen; StateJar sends the minimal memory subset to the model you pick.
keywords: api key setup provider configure openrouter model
---

StateJar does not ship with a model. You bring one.

1. Open **API Keys** in the sidebar.
2. Pick a provider card and paste a key. Keys are encrypted before storage and
   the API never returns one — the list endpoint shows only the last four
   characters.
3. Press **Test connection**. A green result means the key works and the
   provider answered. A red one names the problem in plain language: a bad key,
   an unknown model, or an unreachable address.
4. Go back to **Playground** and choose a model in the picker.

Which to choose:

- **[OpenRouter](#provider.openrouter)** is the easiest start — one key, many
  models, including free ones.
- **[Ollama (local)](#provider.ollama)** keeps every prompt on your own
  computer. Nothing goes to a vendor at all.
- **[Anthropic](#provider.anthropic)**, **[OpenAI](#provider.openai)** and
  **[Google](#provider.gemini)** are direct connections if you already hold a
  key with them.

Whatever you pick, the model is sent the *retrieved subset* for that question —
not your whole memory, and never the raw transcript.
