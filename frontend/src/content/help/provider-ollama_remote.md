---
id: provider.ollama_remote
title: Ollama (remote / cloud)
category: providers
updated_at: 2026-08-04
summary: An Ollama host we call on your behalf. Requires a key.
keywords: ollama remote cloud host key server side
---

**REMOTE · via StateJar server.** Deliberately a separate card from
[Ollama local](#provider.ollama), because the privacy story is different and
collapsing them into one card made that difference invisible.

**Where to get a key.** From whoever runs the host — Ollama Cloud at
`https://ollama.com`, or your own deployment.

**How to configure.** API Keys screen, Ollama (remote) card. Enter the base URL
and an API key. **The base URL has no default**: a remote host is exactly the
case where guessing an address would be wrong. Save, Test connection.

**Why a key is mandatory here.** A local daemon is reachable only from your own
browser, which is its own access control. A remote host is reachable by our
backend, and that is the whole reason a key exists — so this card refuses to
save without one.

**What leaves your machine.** Your question and the minimal memory subset,
**via StateJar's backend**, which forwards them to the host you named. Unlike
the local card, our server does see the prompt in transit. The card says so.

**When it is unavailable.** Errors are translated: a 404 at the address says
the base URL is wrong, an unrecognised model says so by name, and a 200
response carrying `{"error": "Unauthorized"}` — which some hosts return — is
treated as the failure it is rather than as success.
