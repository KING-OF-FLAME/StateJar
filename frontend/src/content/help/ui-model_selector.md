---
id: ui.model_selector
title: Model selector
category: interface
updated_at: 2026-08-04
summary: Choose which model answers, grouped by provider.
keywords: model picker select choose llm dropdown custom
---

Models are grouped by the provider they belong to, with free ones listed
separately from paid ones where a provider offers both. Only providers you have
configured appear.

**Local Ollama models are enumerated by your browser, not by our server.** A
hosted StateJar cannot see `http://localhost:11434`; your tab can. So the list
is whatever you have actually pulled. See [Ollama local](#provider.ollama).

**Custom model** lets you type a model id the catalog does not list, and pick
which provider should route it. Useful for a model released after the catalog
was last refreshed.

If a model you had selected disappears from its provider's catalog, StateJar
falls back to the first available one and tells you rather than failing at send
time.
