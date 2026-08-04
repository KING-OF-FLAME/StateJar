---
id: api.patterns.mcp
title: Pattern 3: MCP
category: api
updated_at: 2026-08-04
summary: Expose StateJar as tools to an MCP-speaking client.
keywords: mcp model context protocol tools pattern integration
---

**Choose this when** your client already speaks the Model Context Protocol and
you want memory as tools the model can call rather than as plumbing you write.

**Status: not shipped.** There is no StateJar MCP package yet. It is described
here because the shape is a decision people ask about while choosing a pattern,
and finding out later is worse than reading it now.

**The shape it would take.** `memory_query` and `memory_ingest` as tools, with
the same scoping model — the namespace resolved from the credential, never
passed by the client.

**What to do today.** Use the [sidecar](#api.patterns.sidecar) from inside your
MCP server. It is the same two calls, and it works now.
