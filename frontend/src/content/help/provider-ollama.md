---
id: provider.ollama
title: Ollama (local)
category: providers
updated_at: 2026-08-04
summary: Runs on your machine. Prompts never leave your computer.
keywords: ollama local llama offline private browser direct origins cors
---

**LOCAL · browser-direct.** This is the only provider where nothing about your
conversation reaches any server, including ours.

**Where to get it.** ollama.com. Install, then pull a model:

```
ollama pull llama3.2
```

**How to configure.** API Keys screen, Ollama (local) card. The base URL
defaults to `http://localhost:11434`. There is **no key field** — a local
daemon does not need one. Save, then **Test connection**.

**How it actually works.** A hosted StateJar backend can never reach
`http://localhost:11434`; that address exists on your machine, not on ours. So
your browser talks to Ollama directly. StateJar's server still does the memory
work — retrieval, handles, audit — but never sees the conversation. The model
list in the picker is enumerated by your browser too, so it is whatever you
have actually pulled.

**What leaves your machine: nothing.** Not the prompt, not the reply. StateJar
supplies only the minimal memory subset, and it supplies it *to your own
browser*, which passes it to your own daemon.

**Origin policy — the one configuration that is required.** Ollama refuses
cross-origin browser requests unless it is started with `OLLAMA_ORIGINS` set to
the page's origin. Without it the request fails as an opaque browser error.
Restart Ollama with:

```
# macOS / Linux
OLLAMA_ORIGINS=https://statejar.com ollama serve

# Windows (cmd)
set OLLAMA_ORIGINS=https://statejar.com
ollama serve

# PowerShell
$env:OLLAMA_ORIGINS="https://statejar.com"; ollama serve
```

Substitute the origin you are actually loading StateJar from — use
`http://localhost:5173` when running the dev server. The card generates the
exact command for your current origin and gives you a copy button, so prefer
that over retyping.

**Base URL forms.** Ollama's own docs write endpoints as
`http://localhost:11434/v1/` and `https://ollama.com/api/chat`, so a pasted
base often already carries a path. StateJar strips a trailing `/api` or `/v1`
rather than appending to it — both forms normalise to the host.

**When it is unavailable.** A dead daemon and a blocked origin both surface to
scripts as the same opaque error, so StateJar distinguishes them by whether
anything is listening at all and tells you which one you have. See
[connection refused](#trouble.ollama-refused) and
[blocked by origin policy](#trouble.ollama-origin).
