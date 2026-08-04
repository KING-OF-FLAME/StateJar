---
id: settings.show_ollama
title: SHOW_OLLAMA
category: settings
updated_at: 2026-08-04
summary: Environment variable SHOW_OLLAMA. Default: False
keywords: show ollama visibility cards toggle
---

**Environment variable:** `SHOW_OLLAMA`

**Default:** `False`


Whether the Ollama provider cards appear in the console.

Off by default on hosted deployments, where most users have no local daemon and
two extra cards are noise. Turn it on for a local install, a workshop, or any
deployment whose users run models themselves.

It controls visibility only. It does not disable the provider.
