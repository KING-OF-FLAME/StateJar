---
id: trouble.ollama-origin
title: Ollama: blocked by origin policy
category: troubleshooting
updated_at: 2026-08-04
summary: Ollama is running and `curl` works, but the browser cannot reach it.
keywords: ollama cors origins blocked browser policy forbidden
---

**Symptom.** Ollama is running and `curl` works, but the browser cannot reach it.

**Likely cause.** Ollama refuses cross-origin browser requests unless it is started with
`OLLAMA_ORIGINS`. `curl` is not a browser and is not subject to this, which is
why the daemon looks healthy from the terminal and unreachable from the page.

The browser hides CORS detail from scripts for security, so the failure arrives
as an opaque error rather than a useful one. StateJar distinguishes it from a
dead daemon by checking whether anything is listening at all.

**Fix.** Restart Ollama with the origin you are loading StateJar from:

```
# macOS / Linux
OLLAMA_ORIGINS=https://statejar.com ollama serve

# Windows (cmd)
set OLLAMA_ORIGINS=https://statejar.com
ollama serve

# PowerShell
$env:OLLAMA_ORIGINS="https://statejar.com"; ollama serve
```

Use `http://localhost:5173` instead when running the dev server. The card
generates the exact command for your current origin with a copy button — use
that rather than retyping. See [Ollama local](#provider.ollama).
