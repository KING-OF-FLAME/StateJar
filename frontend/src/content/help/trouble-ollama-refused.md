---
id: trouble.ollama-refused
title: Ollama: connection refused
category: troubleshooting
updated_at: 2026-08-04
summary: The local Ollama card reports the daemon is not reachable.
keywords: ollama refused connection not reachable serve daemon down
---

**Symptom.** The local Ollama card reports the daemon is not reachable.

**Likely cause.** Nothing is listening at the address. Usually Ollama is not running, or it is running on a different port than the one configured.

**Fix.** Start it:

```
ollama serve
```

Then confirm it answers:

```
curl http://localhost:11434/api/tags
```

If that returns a model list, the daemon is fine and the problem is the base
URL in the card. If it returns nothing, Ollama is not running. If it returns
models but the card still fails, you have the **origin policy** problem instead
— see [blocked by origin policy](#trouble.ollama-origin).
